// File: src/hooks/useDSpaceCollections.js
import { useState, useCallback } from 'react';

/**
 * Hook to get DSpace collections with community context
 * Solves the problem of duplicate collection names
 */
export function useDSpaceCollections() {
  const [collections, setCollections] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  /**
   * Fetch collections with community hierarchy
   */
  const fetchCollections = useCallback(async (dspaceUrl) => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch('/api/dspace/get-collections-with-context', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ dspaceUrl }),
      });

      if (!res.ok) {
        throw new Error('Failed to fetch collections');
      }

      const data = await res.json();
      
      if (data.success) {
        setCollections(data.collections);
        return data.collections;
      } else {
        throw new Error(data.error || 'Unknown error');
      }
    } catch (err) {
      console.error('Error fetching collections:', err);
      setError(err.message);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Find best matching collection using AI extracted metadata
   * Now uses community context for better matching
   */
  const findBestMatch = useCallback((aiMetadata) => {
    if (collections.length === 0) return null;

    // Extract key fields from AI metadata
    const title = aiMetadata.find(m => m.key === 'dc.title')?.value?.toLowerCase() || '';
    const subject = aiMetadata.find(m => m.key === 'dc.subject')?.value?.toLowerCase() || '';
    const type = aiMetadata.find(m => m.key === 'dc.type')?.value?.toLowerCase() || '';
    const department = aiMetadata.find(m => m.key === 'dc.department')?.value?.toLowerCase() || '';
    
    // Faculty/Department abbreviations
    const deptMap = {
      'cntt': 'Công nghệ thông tin',
      'kt': 'Kinh tế',
      'qtkd': 'Quản trị kinh doanh',
      'qt': 'Quản trị',
      'xd': 'Xây dựng',
      'mt': 'Môi trường',
      'nn': 'Ngoại ngữ',
      'dl': 'Du lịch',
      'dt': 'Điện tử',
      'ck': 'Cơ khí',
    };

    // Try to identify department from metadata
    let identifiedDept = '';
    for (const [abbr, fullName] of Object.entries(deptMap)) {
      if (department.includes(abbr) || 
          department.includes(fullName.toLowerCase()) ||
          title.includes(abbr) ||
          subject.includes(abbr)) {
        identifiedDept = fullName;
        break;
      }
    }

    console.log('Matching with:', { title, subject, type, department, identifiedDept });

    // Score each collection
    const scored = collections.map(col => {
      let score = 0;
      const colName = col.name.toLowerCase();
      const communityName = col.communityName.toLowerCase();

      // 1. Match by document type (highest priority)
      if (type) {
        if (type.includes('khóa luận') && colName.includes('khóa luận')) {
          score += 50;
        } else if (type.includes('đồ án') && colName.includes('đồ án')) {
          score += 50;
        } else if (type.includes('giáo trình') && colName.includes('giáo trình')) {
          score += 50;
        } else if (type.includes('tài liệu') && colName.includes('tài liệu')) {
          score += 40;
        } else if (type.includes('luận văn') && colName.includes('luận văn')) {
          score += 50;
        } else if (type.includes('bài giảng') && colName.includes('bài giảng')) {
          score += 50;
        }
      }

      // 2. Match by department (critical for duplicate names!)
      if (identifiedDept) {
        const deptLower = identifiedDept.toLowerCase();
        
        // Check in collection name
        if (colName.includes(deptLower)) {
          score += 100; // Very high score!
        }
        
        // Check in community name (NEW!)
        if (communityName.includes(deptLower)) {
          score += 80;
        }
        
        // Check for abbreviations in collection name
        for (const [abbr, fullName] of Object.entries(deptMap)) {
          if (fullName.toLowerCase() === deptLower) {
            if (colName.includes(abbr)) {
              score += 90;
            }
            if (communityName.includes(abbr)) {
              score += 70;
            }
          }
        }
      }

      // 3. Match by subject keywords
      if (subject) {
        const subjectWords = subject.split(/[,;]+/).map(s => s.trim());
        
        for (const word of subjectWords) {
          if (word && colName.includes(word)) {
            score += 20;
          }
          if (word && communityName.includes(word)) {
            score += 15;
          }
        }
      }

      // 4. Prefer collections with more items (indicates active use)
      if (col.archivedItemsCount > 0) {
        score += Math.min(col.archivedItemsCount / 100, 10);
      }

      return { ...col, score };
    });

    // Sort by score
    scored.sort((a, b) => b.score - a.score);

    console.log('Top 3 matches:', scored.slice(0, 3).map(c => ({
      name: c.displayName,
      score: c.score
    })));

    // Return best match if score is significant
    const best = scored[0];
    if (best && best.score > 30) {
      return best;
    }

    return null;
  }, [collections]);

  /**
   * Group collections by community for display
   */
  const getCollectionsByComm = useCallback(() => {
    const grouped = {};
    
    for (const col of collections) {
      const commName = col.communityName || 'Unknown';
      
      if (!grouped[commName]) {
        grouped[commName] = [];
      }
      
      grouped[commName].push(col);
    }
    
    return grouped;
  }, [collections]);

  return {
    collections,
    loading,
    error,
    fetchCollections,
    findBestMatch,
    getCollectionsByComm,
  };
}