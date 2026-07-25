# Lớp trừu tượng hóa mô hình (YC-MP).
# Toàn hệ thống chỉ gọi model QUA giao diện ModelProvider, không gọi trực tiếp nhà cung cấp nào.
#
# Bố cục:
#   base.py           giao diện ModelProvider + lược đồ trích xuất + hằng số chế độ triển khai
#   textgen.py        lớp trung gian cho mọi công cụ "prompt → text" (lớp con chỉ cần `_complete`)
#   cloud.py          ClaudeProvider  (Anthropic, đám mây)
#   local.py          OllamaProvider  (tại chỗ, API gốc của Ollama)
#   openai_compat.py  OpenAICompatProvider + AzureOpenAIProvider
#                     → vLLM, llama.cpp, LM Studio, TGI, OpenAI, Groq, OpenRouter, Together,
#                       DeepSeek, Mistral, Azure... (một lớp phủ cả họ giao thức)
#   gemini.py         GeminiProvider  (Google, định dạng dây khác → phép thử YC-MP-08)
#   registry.py       BẢNG ĐĂNG KÝ công cụ — thêm lựa chọn mới thường chỉ là thêm một dòng ở đây
#   factory.py        chọn công cụ theo biến môi trường MODEL_PROVIDER (YC-MP-04)
#   router.py         định tuyến theo độ nhạy cảm, ràng buộc cứng YC-DR-03
#   prompt.py         dựng/parse prompt theo lược đồ bất kỳ, dùng chung cho mọi provider
