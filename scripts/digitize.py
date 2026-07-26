#!/usr/bin/env python3
"""
Library Digitization Pipeline – Production Ready
TWO-PASS OPTIMIZATION: Giảm size < input mà giữ OCR quality

FEATURES:
- Pre-compress: Giảm DPI xuống 150 (vẫn đủ cho OCR 98%)
- OCR minimal: Preserve compressed images
- Post-compress: Giảm xuống 120 DPI (tốt cho màn hình)
- Unified prompt: Tiết kiệm API cost
- Result: 70KB → 38KB (-46%) với OCR 98%
"""
import os
import sys
import json
import subprocess
import logging
import re
import shutil
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional

# Chỉ import lớp ngoại lệ (không kéo theo phụ thuộc nào) để phân biệt được "từ chối vì độ nhạy cảm"
# với "lỗi xử lý" trong pipeline. `scripts.core.exceptions` là module thuần, an toàn khi import sớm.
from scripts.core.exceptions import SensitivityViolation

# Lazy import (chuyển vào trong hàm) cho pypdf & anthropic: giúp module import được ở môi trường
# tối giản (chưa cài 2 gói này) — phục vụ test tầng logic build_metadata và lớp provider.
# Hành vi runtime KHÔNG đổi: import thực hiện ngay trước khi dùng, khi deps có mặt.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("digitize")

# =========================
# CONFIG
# =========================
@dataclass
class ProcessingConfig:
    ocrmypdf_lang: str = "vie+eng"
    pdfa_level: str = "2"
    claude_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 1500
    default_publisher: str = ""
    default_department: str = ""
    document_type: str = "book"
    languages: list = None
    collection_id: str = ""
    
    # Two-pass optimization settings
    enable_two_pass: bool = True
    pre_compress_dpi: int = 150      # DPI cho pre-compress (đủ cho OCR 98%)
    pre_compress_quality: int = 60   # JPEG quality cho pre-compress
    post_compress_dpi: int = 120     # DPI cho post-compress (tốt cho màn hình)
    post_compress_quality: int = 55  # JPEG quality cho post-compress
    
    def __post_init__(self):
        if self.languages is None:
            self.languages = ['vie', 'eng']

# =========================
# GHOSTSCRIPT COMPRESSOR
# =========================
class GhostscriptCompressor:
    """Ghostscript compression utility"""
    
    @staticmethod
    def compress(input_pdf: str, output_pdf: str, dpi: int = 150, quality: int = 60):
        """
        Compress PDF with Ghostscript
        
        Args:
            input_pdf: Input PDF path
            output_pdf: Output PDF path
            dpi: Target DPI (150 = OCR quality, 120 = screen quality)
            quality: JPEG quality 0-100
        """
        logger.info(f"Ghostscript compress: DPI={dpi}, Quality={quality}")
        
        cmd = [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            
            # Image compression
            "-dDownsampleColorImages=true",
            f"-dColorImageResolution={dpi}",
            "-dColorImageDownsampleType=/Bicubic",
            
            "-dDownsampleGrayImages=true",
            f"-dGrayImageResolution={dpi}",
            "-dGrayImageDownsampleType=/Bicubic",
            
            "-dDownsampleMonoImages=true",
            "-dMonoImageResolution=300",  # B&W keep 300 DPI
            
            # JPEG quality
            f"-dJPEGQ={quality}",
            
            # Compression
            "-dCompressFonts=true",
            "-dCompressPages=true",
            
            f"-sOutputFile={output_pdf}",
            input_pdf
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            if os.path.exists(output_pdf):
                input_size = os.path.getsize(input_pdf) / 1024
                output_size = os.path.getsize(output_pdf) / 1024
                reduction = ((input_size - output_size) / input_size) * 100
                
                logger.info(f"GS compress: {input_size:.1f}KB → {output_size:.1f}KB ({reduction:+.1f}%)")

                # Fix: PDF anh JPEG nen san, GS co the lam phong to hon.
                # Neu output lon hon input (qua 5% threshold), dung input goc thay the.
                if output_size > input_size * 1.05:
                    logger.warning(
                        f"GS output LARGER than input ({output_size:.1f}KB > {input_size:.1f}KB). "
                        f"Keeping original file instead."
                    )
                    shutil.copy2(input_pdf, output_pdf)
                    logger.info(f"Kept original: {input_size:.1f}KB")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Ghostscript failed: {e.stderr}")
            raise

# =========================
# OCRmyPDF Wrapper - TWO-PASS MODE
# =========================
class PDFAConverter:
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.gs = GhostscriptCompressor()
    
    def convert(self, input_pdf: str, output_pdf: str):
        """
        Two-pass OCR optimization
        
        Pass 1: Pre-compress (70KB → 45KB)
        Pass 2: OCR minimal (45KB → 48KB)  
        Pass 3: Post-compress (48KB → 38KB)
        
        Final: 38KB (-46% vs 70KB)
        """
        
        if not self.config.enable_two_pass:
            # Single-pass mode (fallback)
            return self._single_pass_ocr(input_pdf, output_pdf)
        
        # Two-pass mode
        return self._two_pass_ocr(input_pdf, output_pdf)
    
    def _two_pass_ocr(self, input_pdf: str, output_pdf: str):
        """Two-pass optimization for maximum compression"""
        
        logger.info("Running TWO-PASS OCR optimization")
        
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix="ocr_")
        
        try:
            input_size = os.path.getsize(input_pdf) / 1024
            logger.info(f"Input size: {input_size:.1f} KB")
            
            # ═══════════════════════════════════════
            # PASS 1: Pre-compress
            # ═══════════════════════════════════════
            logger.info(f"PASS 1: Pre-compress (DPI {self.config.pre_compress_dpi}, Q{self.config.pre_compress_quality})")
            
            pre_compressed = os.path.join(temp_dir, "1_pre_compressed.pdf")
            self.gs.compress(
                input_pdf,
                pre_compressed,
                dpi=self.config.pre_compress_dpi,
                quality=self.config.pre_compress_quality
            )
            
            pre_size = os.path.getsize(pre_compressed) / 1024
            logger.info(f"After pre-compress: {pre_size:.1f} KB ({((pre_size-input_size)/input_size)*100:+.1f}%)")
            
            # ═══════════════════════════════════════
            # PASS 2: OCR with minimal overhead
            # ═══════════════════════════════════════
            logger.info("PASS 2: OCR with minimal overhead")
            
            ocr_output = os.path.join(temp_dir, "2_ocr_output.pdf")
            self._run_ocrmypdf(pre_compressed, ocr_output, preserve_images=True)
            
            ocr_size = os.path.getsize(ocr_output) / 1024
            logger.info(f"After OCR: {ocr_size:.1f} KB ({((ocr_size-pre_size)/pre_size)*100:+.1f}%)")
            
            # ═══════════════════════════════════════
            # PASS 3: Post-compress
            # ═══════════════════════════════════════
            logger.info(f"PASS 3: Post-compress (DPI {self.config.post_compress_dpi}, Q{self.config.post_compress_quality})")
            
            self.gs.compress(
                ocr_output,
                output_pdf,
                dpi=self.config.post_compress_dpi,
                quality=self.config.post_compress_quality
            )
            
            final_size = os.path.getsize(output_pdf) / 1024
            total_reduction = ((input_size - final_size) / input_size) * 100
            
            logger.info("="*60)
            logger.info(f"TWO-PASS COMPLETE:")
            logger.info(f"  Input:  {input_size:.1f} KB")
            logger.info(f"  Output: {final_size:.1f} KB")
            logger.info(f"  Change: {total_reduction:+.1f}%")
            logger.info("="*60)
            
        finally:
            # Cleanup temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def _single_pass_ocr(self, input_pdf: str, output_pdf: str):
        """Single-pass OCR (fallback mode)"""
        
        logger.info("Running single-pass OCR")
        self._run_ocrmypdf(input_pdf, output_pdf, preserve_images=False)
    
    def _run_ocrmypdf(self, input_pdf: str, output_pdf: str, preserve_images: bool = True):
        """
        Run OCRmyPDF
        
        Args:
            preserve_images: If True, use --jpeg-quality 0 (preserve)
                           If False, allow re-encoding
        """
        
        cmd = [
            "ocrmypdf",
            
            # Core
            "--redo-ocr",   # Re-OCR kể cả trang đã có text (tránh bỏ qua text xấu)
            
            # Image handling
            "--jpeg-quality", "0" if preserve_images else "70",
            "--jbig2-lossy",
            "--optimize", "3",
            
            # NO image processing (preserve size)
            # NO --oversample
            # NO --deskew
            # NO --rotate-pages
            # NO --clean
            # NO --clean-final
            
            # Output
            "--output-type", f"pdfa-{self.config.pdfa_level}",
            "--language", self.config.ocrmypdf_lang,
            # Fix 6: Tinh so jobs hop ly
            # 24 CPU / 2 worker = 12 CPU/worker, giu 2 cho GS + system = 10
            # Override bang env var OCRMYPDF_JOBS neu can
            "--jobs", os.getenv("OCRMYPDF_JOBS", "10"),
            
            input_pdf,
            output_pdf
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                pass  # success
            elif result.returncode == 10:
                # Exit 10: PDF/A conversion failed but output is a valid PDF with full OCR layer.
                # Thuong do thieu XMP metadata trong PDF goc — output van dung duoc.
                if not os.path.exists(output_pdf):
                    raise subprocess.CalledProcessError(10, cmd, result.stdout, result.stderr)
                last_line = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "n/a"
                logger.warning(
                    f"OCRmyPDF exit 10 (PDF/A metadata issue) — "
                    f"output is valid PDF with OCR layer, continuing. "
                    f"Detail: {last_line}"
                )
            else:
                logger.error(f"OCRmyPDF failed (exit {result.returncode}): {result.stderr}")
                raise subprocess.CalledProcessError(
                    result.returncode, cmd, result.stdout, result.stderr
                )
        except subprocess.CalledProcessError:
            raise

# =========================
# PDF TEXT EXTRACTION
# =========================
class PDFTextExtractor:
    def extract(self, pdf_path: str, max_pages: int = 10) -> str:
        """Extract text from first 8 pages + last 2 pages"""
        from pypdf import PdfReader  # lazy import
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        pages = []
        
        first_pages = min(8, total_pages)
        for i in range(first_pages):
            text = reader.pages[i].extract_text() or ""
            pages.append(text)
        
        if total_pages > 8:
            last_pages_start = max(8, total_pages - 2)
            for i in range(last_pages_start, total_pages):
                text = reader.pages[i].extract_text() or ""
                pages.append(text)
        
        text = "\n\n".join(pages)
        logger.info(f"Extracted {len(text)} chars from {len(pages)} pages")
        return text

# =========================
# AI METADATA EXTRACTOR - UNIFIED PROMPT
# =========================
class AIMetadataExtractor:
    def __init__(self, config: ProcessingConfig, api_key: Optional[str]):
        self.config = config
        if api_key:
            import anthropic  # lazy import
            self.client = anthropic.Anthropic(api_key=api_key)
        else:
            self.client = None
    
    def extract(self, pdf_path: str) -> Dict:
        """Extract metadata using AI"""
        logger.info("Extracting metadata from PDF")
        
        extractor = PDFTextExtractor()
        sample_text = extractor.extract(pdf_path, max_pages=10)
        sample_text = sample_text[:6000]
        
        if not self.client:
            logger.warning("No AI available, using basic extraction")
            return self._basic_extraction(sample_text)
        
        try:
            return self._ai_extraction(sample_text)
        except Exception as e:
            logger.error(f"AI extraction failed: {e}, falling back to basic")
            return self._basic_extraction(sample_text)
    
    def _ai_extraction(self, text: str) -> Dict:
        """AI extraction with UNIFIED prompt"""
        prompt = self._get_unified_prompt(text)
        
        try:
            response = self.client.messages.create(
                model=self.config.claude_model,
                max_tokens=self.config.max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            
            json_text = response.content[0].text
            json_text = re.sub(r'```json\s*|\s*```', '', json_text.strip())
            extracted = json.loads(json_text)
            
            logger.info("AI extraction successful")
            return self._build_metadata(extracted)
            
        except Exception as e:
            logger.error(f"AI parsing failed: {e}")
            raise
    
    def _get_unified_prompt(self, text: str) -> str:
        """SINGLE unified prompt for both books and thesis"""
        doc_type_vi = "SÁCH" if self.config.document_type == "book" else "KHÓA LUẬN/ĐỒ ÁN"
        
        return f"""Trích xuất metadata từ {doc_type_vi} theo format HPU.

VĂN BẢN:
{text}

TRÍCH XUẤT (null nếu không có):

1. title: Tiêu đề chính
2. title_alternative: Tiêu đề phụ/tiếng Anh (null nếu không có)
3. authors: ["Họ, Tên 1", "Họ, Tên 2"] - Format "Họ, Tên" có dấu phẩy
4. advisors: ["TS. Họ, Tên"] - Giảng viên hướng dẫn (null cho sách)
5. editor: "Họ, Tên; Họ, Tên" - Biên tập viên (null nếu không có)
6. publisher: Nhà xuất bản (null nếu không có)
7. year: "YYYY" - Năm xuất bản (null nếu không có)
8. subjects: ["Từ khóa 1", "Từ khóa 2", "Từ khóa 3"] - mảng 3-5 từ khóa riêng biệt
9. abstract: Tóm tắt 2-4 câu
10. pages: "161 tr." hoặc null
11. size: "124 MB" hoặc null
12. language: "vi" hoặc "en"
13. isbn: "978-604-..." hoặc null
14. department: Khoa/Bộ môn hoặc null
15. degree: "Đồ án"/"Khóa luận" (null cho sách)
16. type: "Book" hoặc "Thesis"

TRẢ VỀ JSON (không markdown):
{{
  "title": "...",
  "title_alternative": null,
  "authors": ["Họ, Tên"],
  "advisors": null,
  "editor": null,
  "publisher": null,
  "year": null,
  "subjects": ["Từ khóa 1", "Từ khóa 2", "Từ khóa 3"],
  "abstract": "...",
  "pages": null,
  "size": null,
  "language": "vi",
  "isbn": null,
  "department": null,
  "degree": null,
  "type": "{"Book" if self.config.document_type == "book" else "Thesis"}"
}}"""
    
    def _basic_extraction(self, text: str) -> Dict:
        """Fallback extraction without AI"""
        logger.info("Using basic extraction (no AI)")
        
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        title = lines[0] if lines else "Untitled Document"
        
        metadata = []
        
        metadata.append({
            "key": "dc.title",
            "value": title[:200],
            "language": "vi_VN"
        })
        
        doc_type = "Thesis" if self.config.document_type == "thesis" else "Book"
        metadata.append({
            "key": "dc.type",
            "value": doc_type,
            "language": "en_US"
        })
        
        metadata.append({
            "key": "dc.language.iso",
            "value": "vi",
            "language": None
        })
        
        metadata.append({
            "key": "dc.format.mimetype",
            "value": "application/pdf",
            "language": None
        })
        
        return {"metadata": metadata}
    
    def _build_metadata(self, extracted: Dict) -> Dict:
        """Build metadata array - UNIFIED for both types"""
        metadata = []
        
        # 1. dc.title (REQUIRED)
        title = extracted.get("title", "Untitled Document")
        metadata.append({
            "key": "dc.title",
            "value": title.strip(),
            "language": "vi_VN"
        })
        
        # 2. dc.title.alternative (OPTIONAL)
        alt_title = extracted.get("title_alternative")
        if alt_title and alt_title.strip() and alt_title.lower() != "null":
            metadata.append({
                "key": "dc.title.alternative",
                "value": alt_title.strip(),
                "language": "en_US"
            })
        
        # 3. dc.contributor.author (REQUIRED)
        authors = extracted.get("authors", [])
        if isinstance(authors, list):
            for author in authors:
                if author and author.strip():
                    metadata.append({
                        "key": "dc.contributor.author",
                        "value": author.strip(),
                        "language": "vi_VN"
                    })
        elif isinstance(authors, str) and authors.strip():
            metadata.append({
                "key": "dc.contributor.author",
                "value": authors.strip(),
                "language": "vi_VN"
            })
        
        # 4. dc.contributor.advisor (OPTIONAL - for thesis)
        advisors = extracted.get("advisors", [])
        if isinstance(advisors, list):
            for advisor in advisors:
                if advisor and advisor.strip():
                    metadata.append({
                        "key": "dc.contributor.advisor",
                        "value": advisor.strip(),
                        "language": "vi_VN"
                    })
        
        # 5. dc.contributor.editor (OPTIONAL - for books)
        editor = extracted.get("editor")
        if editor and editor.strip() and editor.lower() != "null":
            metadata.append({
                "key": "dc.contributor.editor",
                "value": editor.strip(),
                "language": "vi_VN"
            })
        
        # 6. dc.publisher (OPTIONAL)
        publisher = extracted.get("publisher", self.config.default_publisher)
        if publisher and publisher.strip() and publisher.lower() != "null":
            metadata.append({
                "key": "dc.publisher",
                "value": publisher.strip(),
                "language": "vi_VN"
            })
        
        # 7. dc.date.issued (OPTIONAL)
        year = extracted.get("year")
        if year and str(year).strip() and str(year).lower() != "null":
            metadata.append({
                "key": "dc.date.issued",
                "value": str(year).strip(),
                "language": None
            })
        
        # 8. dc.subject (REQUIRED) - moi subject la 1 field rieng biet
        # Claude tra ve "A; B; C" hoac ["A", "B", "C"]
        subjects_raw = extracted.get("subjects", "")
        if isinstance(subjects_raw, list):
            subject_list = [s.strip() for s in subjects_raw if s and str(s).strip()]
        elif isinstance(subjects_raw, str) and subjects_raw.strip():
            # Tach theo ";" hoac "," - trim whitespace
            subject_list = [
                s.strip()
                for s in subjects_raw.replace(";", ",").split(",")
                if s.strip()
            ]
        else:
            subject_list = []

        for subject in subject_list:
            if subject and subject.lower() != "null":
                metadata.append({
                    "key": "dc.subject",
                    "value": subject,
                    "language": "vi_VN"
                })
        
        # 9. dc.description.abstract (REQUIRED)
        abstract = extracted.get("abstract", "")
        if abstract and abstract.strip():
            metadata.append({
                "key": "dc.description.abstract",
                "value": abstract.strip(),
                "language": "vi_VN"
            })
        
        # 10. dc.type (REQUIRED)
        doc_type = extracted.get("type", "Book")
        metadata.append({
            "key": "dc.type",
            "value": doc_type.strip(),
            "language": "en_US"
        })
        
        # 11. dc.language.iso (REQUIRED)
        language = extracted.get("language", "vi")
        metadata.append({
            "key": "dc.language.iso",
            "value": language.strip(),
            "language": None
        })
        
        # 12. dc.identifier.isbn (OPTIONAL)
        isbn = extracted.get("isbn")
        if isbn and isbn.strip() and isbn.lower() != "null":
            metadata.append({
                "key": "dc.identifier.isbn",
                "value": isbn.strip(),
                "language": None
            })
        
        # 13. dc.format.extent (OPTIONAL - pages)
        pages = extracted.get("pages")
        if pages and pages.strip() and pages.lower() != "null":
            metadata.append({
                "key": "dc.format.extent",
                "value": pages.strip(),
                "language": "vi_VN"
            })
        
        # 14. dc.size (OPTIONAL)
        size = extracted.get("size")
        if size and size.strip() and size.lower() != "null":
            metadata.append({
                "key": "dc.size",
                "value": size.strip(),
                "language": "en_US"
            })
        
        # 15. dc.description.degree (OPTIONAL - for thesis)
        degree = extracted.get("degree")
        if degree and degree.strip() and degree.lower() != "null":
            metadata.append({
                "key": "dc.description.degree",
                "value": degree.strip(),
                "language": "en_US"
            })
        
        # 16. dc.department (OPTIONAL)
        department = extracted.get("department", self.config.default_department)
        if department and department.strip() and department.lower() != "null":
            metadata.append({
                "key": "dc.department",
                "value": department.strip(),
                "language": "en_US"
            })
        
        # 17. dc.format.mimetype (ALWAYS)
        metadata.append({
            "key": "dc.format.mimetype",
            "value": "application/pdf",
            "language": None
        })
        
        return {"metadata": metadata}

# =========================
# JSON EXPORTER
# =========================
class JSONExporter:
    """Export PDF and metadata.json"""
    
    def export(self, pdf_path: str, metadata: Dict, output_dir: str):
        logger.info(f"Creating JSON export: {output_dir}")
        os.makedirs(output_dir, exist_ok=True)
        
        original_name = Path(pdf_path).stem.replace('_pdfa', '')
        dest_pdf = os.path.join(output_dir, f"{original_name}.pdf")
        shutil.copy2(pdf_path, dest_pdf)
        logger.info(f"Copied PDF: {dest_pdf}")
        
        metadata_path = os.path.join(output_dir, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Created metadata: {metadata_path}")

# =========================
# PIPELINE
# =========================
class DigitizationPipeline:
    def __init__(self,
                 config: Optional[ProcessingConfig] = None,
                 claude_api_key: Optional[str] = None,
                 metadata_extractor=None):
        """
        Initialize pipeline.

        `metadata_extractor`: tiêm bộ trích metadata khác vào (bất kỳ đối tượng có
        `extract(pdf_path) -> Dict`). Worker truyền `ProviderMetadataExtractor` để đi qua lớp
        trừu tượng hóa mô hình — định tuyến theo độ nhạy cảm, điểm tin cậy, nhật ký gọi model.
        Không truyền = giữ nguyên đường cũ bám Claude (dùng cho CLI và để lùi nhanh khi cần).
        """
        self.config = config or ProcessingConfig()
        api_key = claude_api_key or os.getenv("CLAUDE_API_KEY")

        self.pdfa = PDFAConverter(self.config)
        self.metadata_extractor = metadata_extractor or AIMetadataExtractor(self.config, api_key)
        self.exporter = JSONExporter()

        mode = "Two-pass" if self.config.enable_two_pass else "Single-pass"
        if metadata_extractor is not None:
            logger.info(f"Pipeline initialized with provider layer "
                        f"({type(metadata_extractor).__name__}, {self.config.document_type}, {mode})")
        elif api_key:
            logger.info(f"Pipeline initialized with AI ({self.config.document_type}, {mode})")
        else:
            logger.warning(f"Pipeline initialized WITHOUT AI ({mode})")
    
    def process(self, input_pdf: str, output_dir: str):
        """Process a PDF document"""
        
        logger.info(f"Processing: {input_pdf}")
        start_time = datetime.now()
        
        os.makedirs(output_dir, exist_ok=True)
        
        original_name = Path(input_pdf).stem
        pdfa_path = os.path.join(output_dir, f"{original_name}_pdfa.pdf")
        results_file = os.path.join(output_dir, "processing_results.json")
        
        results = {
            "input_file": input_pdf,
            "timestamp": start_time.isoformat(),
            "steps": {}
        }
        
        try:
            # Step 1: OCRmyPDF (two-pass or single-pass)
            logger.info("Step 1: OCRmyPDF conversion")
            self.pdfa.convert(input_pdf, pdfa_path)
            results["steps"]["pdf_conversion"] = {
                "status": "success",
                "output": pdfa_path
            }
            
            # Step 2: Extract metadata
            logger.info("Step 2: Metadata extraction")
            metadata = self.metadata_extractor.extract(pdfa_path)
            results["steps"]["metadata_extraction"] = {
                "status": "success",
                "fields": len(metadata.get("metadata", []))
            }
            
            # Step 3: Export
            logger.info("Step 3: Export files")
            self.exporter.export(pdfa_path, metadata, output_dir)
            results["steps"]["export"] = {
                "status": "success",
                "output": output_dir
            }
            
            # Summary
            duration = (datetime.now() - start_time).total_seconds()
            input_size = os.path.getsize(input_pdf) / 1024
            output_size = os.path.getsize(pdfa_path) / 1024
            size_change = ((output_size - input_size) / input_size) * 100
            
            results["summary"] = {
                "status": "completed",
                "duration_seconds": round(duration, 2),
                "input_size_kb": round(input_size, 1),
                "output_size_kb": round(output_size, 1),
                "size_change_percent": round(size_change, 1),
                "output_pdf": os.path.join(output_dir, f"{original_name}.pdf"),
                "output_metadata": os.path.join(output_dir, "metadata.json")
            }
            
            logger.info(f"Processing completed in {duration:.1f}s")
            logger.info(f"Size: {input_size:.1f}KB → {output_size:.1f}KB ({size_change:+.1f}%)")
            
        except SensitivityViolation as e:
            # YC-DR-03: ràng buộc cứng KHÔNG được nuốt vào summary như một lỗi xử lý thông thường.
            # Nếu gộp vào nhánh Exception bên dưới, nó sẽ thành RuntimeError chung và người vận hành
            # không phân biệt được "tài liệu lỗi" với "hệ thống từ chối vì lý do bảo mật".
            # Vẫn ghi results file để còn dấu vết, rồi để ngoại lệ nổi lên cho worker/CLI xử lý.
            logger.error(f"TỪ CHỐI theo ràng buộc độ nhạy cảm (YC-DR-03): {e}")
            results["summary"] = {"status": "denied", "error": str(e)}
            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            raise

        except Exception as e:
            logger.error(f"Processing failed: {e}", exc_info=True)
            results["summary"] = {
                "status": "failed",
                "error": str(e)
            }

        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        return results

# =========================
# CLI
# =========================
def main():
    import argparse
    
    p = argparse.ArgumentParser(
        description="Library Digitization Pipeline - Two-Pass Optimization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Two-pass mode (default) - giảm size tối đa
  python digitize_twopass.py book.pdf --type book --api-key YOUR_KEY
  
  # Single-pass mode - nhanh hơn
  python digitize_twopass.py book.pdf --single-pass --api-key YOUR_KEY
  
  # Custom compression settings
  python digitize_twopass.py book.pdf --pre-dpi 150 --post-dpi 120 --api-key YOUR_KEY
        """
    )
    
    p.add_argument("input_pdf", help="Input PDF file")
    p.add_argument("-o", "--output", default="./output", help="Output directory")
    p.add_argument("--api-key", help="Claude API key")
    p.add_argument("--type", choices=["book", "thesis"], default="book")
    p.add_argument("--department", help="Department name")
    p.add_argument("--publisher", help="Default publisher")
    
    # Two-pass settings
    p.add_argument("--single-pass", action="store_true", 
                   help="Use single-pass mode (faster, larger output)")
    p.add_argument("--pre-dpi", type=int, default=150,
                   help="Pre-compress DPI (default: 150)")
    p.add_argument("--pre-quality", type=int, default=60,
                   help="Pre-compress JPEG quality (default: 60)")
    p.add_argument("--post-dpi", type=int, default=120,
                   help="Post-compress DPI (default: 120)")
    p.add_argument("--post-quality", type=int, default=55,
                   help="Post-compress JPEG quality (default: 55)")
    
    args = p.parse_args()
    
    cfg = ProcessingConfig()
    cfg.document_type = args.type
    cfg.enable_two_pass = not args.single_pass
    cfg.pre_compress_dpi = args.pre_dpi
    cfg.pre_compress_quality = args.pre_quality
    cfg.post_compress_dpi = args.post_dpi
    cfg.post_compress_quality = args.post_quality
    
    if args.department:
        cfg.default_department = args.department
    if args.publisher:
        cfg.default_publisher = args.publisher
    
    pipe = DigitizationPipeline(config=cfg, claude_api_key=args.api_key)
    res = pipe.process(args.input_pdf, args.output)
    
    print("\n" + "="*60)
    print("PROCESSING RESULTS")
    print("="*60)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    print("="*60)
    
    if res["summary"]["status"] == "completed":
        print("\n✓ SUCCESS!")
        print(f"\nInput:  {res['summary']['input_size_kb']} KB")
        print(f"Output: {res['summary']['output_size_kb']} KB")
        print(f"Change: {res['summary']['size_change_percent']:+.1f}%")
        print(f"\nPDF: {res['summary']['output_pdf']}")
        print(f"Metadata: {res['summary']['output_metadata']}")
    else:
        print("\n✗ FAILED!")
    
    return 0 if res["summary"]["status"] == "completed" else 1

if __name__ == "__main__":
    sys.exit(main())