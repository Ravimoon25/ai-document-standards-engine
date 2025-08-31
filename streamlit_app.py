# COMPLETE IMPORTS SECTION FOR YOUR streamlit_app.py

# Your existing imports (keep these):
import streamlit as st
import os
from google import genai
from google.genai import types
import PIL.Image
import io
from datetime import datetime
import json
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import docx
import PyPDF2
import re
from typing import List, Dict, Tuple

# NEW imports to ADD for agent system:
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# NEW enhanced DOCX imports to ADD:
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.shared import OxmlElement, qn


# Add these classes after your imports and before your existing functions

class AgentType(Enum):
    """Enumeration of available agent types"""
    CONTENT_EDITOR = "content_editor"
    FORMATTER = "formatter" 
    QUALITY_CHECKER = "quality_checker"

@dataclass
class ProcessingResult:
    """Standardized result format for all agents"""
    content: str
    instructions: List[Dict]
    metadata: Dict
    agent_notes: str
    success: bool = True
    error_message: str = ""

class BaseAgent:
    """Base class for all document processing agents"""
    
    def __init__(self, agent_type: AgentType, standards_retriever=None):
        self.agent_type = agent_type
        self.standards_retriever = standards_retriever
        self.client = None
        
        # Initialize AI client
        try:
            self.client = get_client()
        except Exception as e:
            st.error(f"Failed to initialize {agent_type.value} agent: {str(e)}")
    
    def process(self, input_data: Dict) -> ProcessingResult:
        """Process input data and return standardized result"""
        raise NotImplementedError("Subclasses must implement process method")
    
    def _parse_json_response(self, response_text: str, fallback_content: str = "") -> Dict:
        """Helper method to parse JSON from AI responses with fallback"""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError as e:
            st.warning(f"JSON parsing failed: {str(e)}")
        except Exception as e:
            st.warning(f"Response parsing error: {str(e)}")
        
        # Return fallback structure
        return {
            "content": fallback_content or response_text,
            "instructions": [],
            "metadata": {},
            "agent_notes": f"Fallback response due to parsing error"
        }
    
    def _get_ai_response(self, prompt: str) -> str:
        """Helper method to get AI response with error handling"""
        if not self.client:
            return "Error: AI client not initialized"
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash-image-preview",
                contents=prompt
            )
            
            result_text = ""
            for part in response.parts:
                if part.text:
                    result_text += part.text
            
            return result_text
            
        except Exception as e:
            error_msg = f"AI response error: {str(e)}"
            st.error(error_msg)
            return error_msg

class EnhancedStandardsRetriever:
    """Enhanced RAG system with filtering capabilities for agents"""
    
    def __init__(self):
        self.processor = StandardsProcessor()
    
    def search(self, query: str, filter_types: List[str] = None, top_k: int = 5) -> List[Dict]:
        """Search with optional filtering by standard type"""
        
        # Check if RAG system is available
        if not st.session_state.standards_chunks:
            st.warning("Standards knowledge base not built yet")
            return []
        
        try:
            # Get base search results (get more for filtering)
            results = self.processor.semantic_search(query, top_k=top_k*2)
            
            # Apply type filtering if specified
            if filter_types:
                filtered_results = []
                for result in results:
                    # Check if the source document type matches filter
                    source_standard = self._find_source_standard(result['doc_name'])
                    if source_standard and source_standard.get('type') in filter_types:
                        filtered_results.append(result)
                        if len(filtered_results) >= top_k:
                            break
                
                return filtered_results
            
            return results[:top_k]
            
        except Exception as e:
            st.error(f"Standards retrieval error: {str(e)}")
            return []
    
    def _find_source_standard(self, doc_name: str) -> Optional[Dict]:
        """Find the original standard document by name"""
        for standard in st.session_state.standards_library:
            if standard['name'] == doc_name:
                return standard
        return None
    
    def get_available_standard_types(self) -> List[str]:
        """Get list of all available standard types"""
        types = set()
        for standard in st.session_state.standards_library:
            types.add(standard.get('type', 'Unknown'))
        return list(types)
    
    def get_standards_count_by_type(self) -> Dict[str, int]:
        """Get count of standards by type"""
        counts = {}
        for standard in st.session_state.standards_library:
            std_type = standard.get('type', 'Unknown')
            counts[std_type] = counts.get(std_type, 0) + 1
        return counts

# Helper function for agent status display
def display_agent_status(retriever: EnhancedStandardsRetriever):
    """Display current status of agents based on available standards"""
    
    st.subheader("Agent System Status")
    
    # Get standards count by type
    standards_by_type = retriever.get_standards_count_by_type()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Content Editor Agent**")
        content_types = ['Editorial Guidelines', 'Style Guide', 'Writing Standards']
        content_count = sum(standards_by_type.get(t, 0) for t in content_types)
        
        if content_count > 0:
            st.success(f"Ready ({content_count} standards)")
        else:
            st.warning("No content standards loaded")
    
    with col2:
        st.markdown("**Formatting Agent**") 
        format_types = ['Formatting Standards', 'Template Rules', 'Layout Guidelines']
        format_count = sum(standards_by_type.get(t, 0) for t in format_types)
        
        if format_count > 0:
            st.success(f"Ready ({format_count} standards)")
        else:
            st.warning("No formatting standards loaded")
    
    with col3:
        st.markdown("**Quality Assurance Agent**")
        quality_types = ['Quality Standards', 'Compliance Rules', 'Review Checklist']
        quality_count = sum(standards_by_type.get(t, 0) for t in quality_types)
        
        if quality_count > 0:
            st.success(f"Ready ({quality_count} standards)")
        else:
            st.warning("No quality standards loaded")
    
    # Show available standard types
    if standards_by_type:
        with st.expander("Available Standard Types"):
            for std_type, count in standards_by_type.items():
                st.write(f"• {std_type}: {count} documents")
    
    return content_count > 0, format_count > 0, quality_count > 0


class ContentStandardsAgent(BaseAgent):
    """Agent responsible for applying editorial and writing standards"""
    
    def __init__(self, standards_retriever):
        super().__init__(AgentType.CONTENT_EDITOR, standards_retriever)
    
    def process(self, input_data: Dict) -> ProcessingResult:
        """Apply content standards to document text"""
        
        document_text = input_data.get('document_text', '')
        if not document_text.strip():
            return ProcessingResult(
                content="",
                instructions=[],
                metadata={},
                agent_notes="No document text provided",
                success=False,
                error_message="Empty document text"
            )
        
        try:
            # Retrieve relevant content standards
            content_standards = self.standards_retriever.search(
                query=f"editorial writing style guidelines grammar citation format {document_text[:300]}",
                filter_types=['Editorial Guidelines', 'Style Guide', 'Writing Standards'],
                top_k=6
            )
            
            if not content_standards:
                st.warning("No content standards found for document processing")
                return ProcessingResult(
                    content=document_text,
                    instructions=[],
                    metadata={'standards_found': 0},
                    agent_notes="No relevant content standards found - document unchanged",
                    success=True
                )
            
            # Build content editing prompt
            standards_context = "\n".join([
                f"STANDARD RULE ({std['doc_name']}): {std['text'][:500]}"
                for std in content_standards
            ])
            
            prompt = f"""
You are a Content Standards Agent for academic document processing. Apply editorial standards to improve document content while maintaining academic integrity.

CONTENT STANDARDS TO APPLY:
{standards_context}

DOCUMENT TO EDIT:
{document_text}

TASKS:
1. Apply writing style improvements (clarity, conciseness, academic tone)
2. Fix citation formatting according to standards
3. Improve paragraph structure and flow
4. Ensure consistency in terminology
5. Correct grammar and punctuation
6. Maintain original meaning and content

RESPOND IN EXACTLY THIS JSON FORMAT:
{{
    "edited_content": "The complete improved document text with all editorial improvements applied",
    "content_changes": [
        "Specific change 1 made",
        "Specific change 2 made",
        "Specific change 3 made"
    ],
    "formatting_hints": [
        {{"element": "title", "instruction": "Apply title formatting"}},
        {{"element": "headings", "instruction": "Use standard heading hierarchy"}},
        {{"element": "citations", "instruction": "Format according to APA/MLA style"}},
        {{"element": "references", "instruction": "Apply standard reference formatting"}}
    ],
    "agent_notes": "Summary of editorial improvements made and rationale"
}}

IMPORTANT: Return ONLY valid JSON. No additional text or explanations outside the JSON structure.
"""
            
            # Get AI response
            response_text = self._get_ai_response(prompt)
            
            # Parse response
            parsed_response = self._parse_json_response(response_text, document_text)
            
            # Validate and clean response
            edited_content = parsed_response.get('edited_content', document_text)
            content_changes = parsed_response.get('content_changes', [])
            formatting_hints = parsed_response.get('formatting_hints', [])
            agent_notes = parsed_response.get('agent_notes', 'Content processing completed')
            
            # Ensure content is not empty
            if not edited_content.strip():
                edited_content = document_text
                agent_notes += " (Original content preserved due to empty result)"
            
            return ProcessingResult(
                content=edited_content,
                instructions=formatting_hints,
                metadata={
                    'content_changes': content_changes,
                    'standards_applied': len(content_standards),
                    'original_word_count': len(document_text.split()),
                    'edited_word_count': len(edited_content.split())
                },
                agent_notes=agent_notes,
                success=True
            )
            
        except Exception as e:
            error_msg = f"Content agent processing error: {str(e)}"
            st.error(error_msg)
            
            return ProcessingResult(
                content=document_text,  # Return original content on error
                instructions=[],
                metadata={'error': error_msg},
                agent_notes="Processing failed - original content preserved",
                success=False,
                error_message=error_msg
            )
    
    def preview_standards(self, document_text: str, max_standards: int = 5) -> List[Dict]:
        """Preview which content standards would be applied to a document"""
        
        if not self.standards_retriever:
            return []
        
        try:
            standards = self.standards_retriever.search(
                query=f"editorial writing style guidelines {document_text[:200]}",
                filter_types=['Editorial Guidelines', 'Style Guide', 'Writing Standards'],
                top_k=max_standards
            )
            
            return standards
            
        except Exception as e:
            st.error(f"Standards preview error: {str(e)}")
            return []


class FormattingAgent(BaseAgent):
    """Agent responsible for applying visual formatting standards to documents"""
    
    def __init__(self, standards_retriever):
        super().__init__(AgentType.FORMATTER, standards_retriever)
    
    def process(self, input_data: Dict) -> ProcessingResult:
        """Apply formatting standards to create structured DOCX instructions"""
        
        content = input_data.get('content', '')
        content_hints = input_data.get('formatting_hints', [])
        
        if not content.strip():
            return ProcessingResult(
                content="",
                instructions=[],
                metadata={},
                agent_notes="No content provided for formatting",
                success=False,
                error_message="Empty content"
            )
        
        try:
            # Retrieve formatting standards
            formatting_standards = self.standards_retriever.search(
                query="document formatting styles fonts margins headings layout spacing citations tables",
                filter_types=['Formatting Standards', 'Template Rules', 'Layout Guidelines'],
                top_k=8
            )
            
            # Build comprehensive formatting instructions
            standards_context = "\n".join([
                f"FORMAT RULE ({std['doc_name']}): {std['text'][:400]}"
                for std in formatting_standards
            ])
            
            # Include content hints from previous agent
            hints_context = ""
            if content_hints:
                hints_context = "CONTENT AGENT SUGGESTIONS:\n" + "\n".join([
                    f"- {hint.get('element', 'element')}: {hint.get('instruction', 'apply formatting')}"
                    for hint in content_hints
                ])
            
            prompt = f"""
You are a Document Formatting Agent. Create detailed DOCX formatting instructions for academic document publishing.

FORMATTING STANDARDS:
{standards_context}

{hints_context}

CONTENT TO FORMAT:
{content}

ANALYZE the content and create comprehensive DOCX formatting plan with these requirements:

1. Identify document structure (title, headings, paragraphs, lists, tables, citations)
2. Apply appropriate formatting styles for each element
3. Ensure academic publishing standards
4. Specify fonts, sizes, spacing, and alignment

RESPOND IN EXACTLY THIS JSON FORMAT:
{{
    "document_structure": [
        {{"type": "title", "text": "Main document title", "style": "Title", "alignment": "center", "font_size": 16, "bold": true}},
        {{"type": "author", "text": "Author information", "style": "Normal", "alignment": "center", "font_size": 12}},
        {{"type": "heading", "level": 1, "text": "Section heading", "style": "Heading 1", "font_size": 14, "bold": true}},
        {{"type": "heading", "level": 2, "text": "Subsection heading", "style": "Heading 2", "font_size": 13, "bold": true}},
        {{"type": "paragraph", "text": "Paragraph content", "style": "Normal", "alignment": "justify", "font_size": 12}},
        {{"type": "list", "style": "bullet", "items": ["item1", "item2"], "font_size": 12}},
        {{"type": "citation", "text": "Citation text", "style": "Citation", "font_size": 10, "italic": true}},
        {{"type": "table", "headers": ["col1", "col2"], "rows": [["data1", "data2"]], "style": "Table Grid"}}
    ],
    "document_settings": {{
        "font_family": "Times New Roman",
        "default_font_size": 12,
        "line_spacing": 1.5,
        "margins": {{"top": 1.0, "bottom": 1.0, "left": 1.0, "right": 1.0}},
        "page_orientation": "portrait"
    }},
    "style_definitions": [
        {{"name": "Citation", "font_size": 10, "italic": true, "color": "black"}},
        {{"name": "Abstract", "font_size": 11, "italic": true, "alignment": "justify"}},
        {{"name": "Keywords", "font_size": 11, "bold": true}}
    ],
    "agent_notes": "Detailed explanation of formatting decisions and standards applied"
}}

IMPORTANT: 
- Analyze the ENTIRE content and create structure for ALL elements
- Use appropriate academic formatting standards
- Return ONLY valid JSON, no additional text
- Ensure all text from content is included in document_structure
"""
            
            # Get AI response
            response_text = self._get_ai_response(prompt)
            
            # Parse response with fallback
            parsed_response = self._parse_json_response(response_text, content)
            
            # Extract and validate formatting data
            document_structure = parsed_response.get('document_structure', [])
            document_settings = parsed_response.get('document_settings', self._get_default_settings())
            style_definitions = parsed_response.get('style_definitions', [])
            agent_notes = parsed_response.get('agent_notes', 'Formatting instructions generated')
            
            # If no structure generated, create basic fallback
            if not document_structure:
                document_structure = self._create_fallback_structure(content)
                agent_notes += " (Using fallback structure due to parsing issues)"
            
            # Validate structure completeness
            total_content_length = sum(len(item.get('text', '')) for item in document_structure)
            if total_content_length < len(content) * 0.8:  # Less than 80% of content structured
                st.warning("Formatting may be incomplete - some content might be missing")
            
            return ProcessingResult(
                content=content,
                instructions=document_structure,
                metadata={
                    'document_settings': document_settings,
                    'style_definitions': style_definitions,
                    'standards_applied': len(formatting_standards),
                    'structure_elements': len(document_structure)
                },
                agent_notes=agent_notes,
                success=True
            )
            
        except Exception as e:
            error_msg = f"Formatting agent error: {str(e)}"
            st.error(error_msg)
            
            # Create basic fallback formatting
            fallback_structure = self._create_fallback_structure(content)
            
            return ProcessingResult(
                content=content,
                instructions=fallback_structure,
                metadata={
                    'document_settings': self._get_default_settings(),
                    'error': error_msg
                },
                agent_notes="Fallback formatting applied due to processing error",
                success=False,
                error_message=error_msg
            )
    
    def _get_default_settings(self) -> Dict:
        """Return default document settings"""
        return {
            "font_family": "Times New Roman",
            "default_font_size": 12,
            "line_spacing": 1.5,
            "margins": {"top": 1.0, "bottom": 1.0, "left": 1.0, "right": 1.0},
            "page_orientation": "portrait"
        }
    
    def _create_fallback_structure(self, content: str) -> List[Dict]:
        """Create basic document structure when AI parsing fails"""
        
        structure = []
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Try to identify element types
            if len(line) < 100 and (line.isupper() or line.endswith(':')):
                # Likely a heading
                structure.append({
                    "type": "heading",
                    "level": 1,
                    "text": line,
                    "style": "Heading 1",
                    "font_size": 14,
                    "bold": True
                })
            elif line.startswith(('•', '-', '*')):
                # List item
                structure.append({
                    "type": "list",
                    "style": "bullet",
                    "items": [line[1:].strip()],
                    "font_size": 12
                })
            else:
                # Regular paragraph
                structure.append({
                    "type": "paragraph",
                    "text": line,
                    "style": "Normal",
                    "alignment": "justify",
                    "font_size": 12
                })
        
        return structure
    
    def preview_formatting_plan(self, content: str) -> Dict:
        """Preview formatting plan without full processing"""
        
        try:
            # Quick analysis of content structure
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            
            analysis = {
                'total_lines': len(lines),
                'estimated_paragraphs': len([line for line in lines if len(line) > 50]),
                'potential_headings': len([line for line in lines if len(line) < 100 and line.istitle()]),
                'list_items': len([line for line in lines if line.startswith(('•', '-', '*'))]),
                'formatting_complexity': 'Simple' if len(lines) < 20 else 'Medium' if len(lines) < 50 else 'Complex'
            }
            
            return analysis
            
        except Exception as e:
            return {'error': str(e)}


class QualityAssuranceAgent(BaseAgent):
    """Agent responsible for final quality checks and compliance validation"""
    
    def __init__(self, standards_retriever):
        super().__init__(AgentType.QUALITY_CHECKER, standards_retriever)
    
    def process(self, input_data: Dict) -> ProcessingResult:
        """Perform quality assurance checks on processed document"""
        
        content = input_data.get('content', '')
        formatting_instructions = input_data.get('instructions', [])
        document_settings = input_data.get('document_settings', {})
        
        if not content.strip():
            return ProcessingResult(
                content="",
                instructions=[],
                metadata={},
                agent_notes="No content provided for quality check",
                success=False,
                error_message="Empty content for quality assurance"
            )
        
        try:
            # Retrieve quality and compliance standards
            quality_standards = self.standards_retriever.search(
                query="quality assurance compliance document review checklist validation requirements",
                filter_types=['Quality Standards', 'Compliance Rules', 'Review Checklist'],
                top_k=5
            )
            
            # Build quality assessment context
            standards_context = "\n".join([
                f"QUALITY RULE ({std['doc_name']}): {std['text'][:300]}"
                for std in quality_standards
            ])
            
            prompt = f"""
You are a Quality Assurance Agent for academic document publishing. Perform comprehensive quality review.

QUALITY STANDARDS:
{standards_context}

DOCUMENT CONTENT TO REVIEW:
{content[:2000]}...

FORMATTING APPLIED:
{json.dumps(formatting_instructions[:10], indent=2)}

DOCUMENT SETTINGS:
{json.dumps(document_settings, indent=2)}

PERFORM QUALITY ASSESSMENT:

1. Content Quality Review:
   - Check for academic writing standards
   - Verify citation consistency
   - Assess clarity and coherence
   - Check for grammatical errors

2. Formatting Compliance:
   - Verify proper heading hierarchy
   - Check font and spacing consistency
   - Validate style application
   - Ensure proper document structure

3. Completeness Check:
   - Verify all content is formatted
   - Check for missing elements
   - Validate document integrity

RESPOND IN EXACTLY THIS JSON FORMAT:
{{
    "compliance_score": 85,
    "quality_assessment": {{
        "content_quality": {{"score": 90, "issues": ["Issue 1", "Issue 2"]}},
        "formatting_compliance": {{"score": 85, "issues": ["Format issue 1"]}},
        "completeness": {{"score": 95, "issues": []}}
    }},
    "critical_issues": [
        "Critical issue requiring immediate attention"
    ],
    "recommendations": [
        "Specific improvement recommendation 1",
        "Specific improvement recommendation 2"
    ],
    "final_approval": true,
    "quality_improvements": [
        {{"type": "heading", "level": 1, "text": "Corrected heading", "reason": "Fixed capitalization"}},
        {{"type": "paragraph", "text": "Improved paragraph", "reason": "Enhanced clarity"}}
    ],
    "agent_notes": "Comprehensive quality assessment summary and final approval status"
}}

IMPORTANT: Return ONLY valid JSON. Be thorough in assessment but practical in recommendations.
"""
            
            # Get AI response
            response_text = self._get_ai_response(prompt)
            
            # Parse response
            parsed_response = self._parse_json_response(response_text, content)
            
            # Extract quality data
            compliance_score = parsed_response.get('compliance_score', 75)
            quality_assessment = parsed_response.get('quality_assessment', {})
            critical_issues = parsed_response.get('critical_issues', [])
            recommendations = parsed_response.get('recommendations', [])
            final_approval = parsed_response.get('final_approval', True)
            quality_improvements = parsed_response.get('quality_improvements', [])
            agent_notes = parsed_response.get('agent_notes', 'Quality review completed')
            
            # Apply quality improvements to instructions if any
            final_instructions = self._apply_quality_improvements(
                formatting_instructions, 
                quality_improvements
            )
            
            # Determine overall quality status
            quality_status = self._determine_quality_status(compliance_score, critical_issues)
            
            return ProcessingResult(
                content=content,
                instructions=final_instructions,
                metadata={
                    'compliance_score': compliance_score,
                    'quality_assessment': quality_assessment,
                    'critical_issues': critical_issues,
                    'recommendations': recommendations,
                    'final_approval': final_approval,
                    'quality_status': quality_status,
                    'standards_checked': len(quality_standards)
                },
                agent_notes=agent_notes,
                success=final_approval and len(critical_issues) == 0
            )
            
        except Exception as e:
            error_msg = f"Quality assurance error: {str(e)}"
            st.error(error_msg)
            
            # Perform basic quality check as fallback
            basic_assessment = self._perform_basic_quality_check(content, formatting_instructions)
            
            return ProcessingResult(
                content=content,
                instructions=formatting_instructions,
                metadata={
                    'compliance_score': basic_assessment['score'],
                    'quality_assessment': basic_assessment,
                    'error': error_msg
                },
                agent_notes="Basic quality check performed due to processing error",
                success=False,
                error_message=error_msg
            )
    
    def _apply_quality_improvements(self, original_instructions: List[Dict], 
                                  improvements: List[Dict]) -> List[Dict]:
        """Apply quality improvements to formatting instructions"""
        
        if not improvements:
            return original_instructions
        
        improved_instructions = original_instructions.copy()
        
        # Apply improvements (simple implementation)
        for improvement in improvements:
            improvement_type = improvement.get('type')
            improved_text = improvement.get('text', '')
            
            # Find and update matching instruction
            for i, instruction in enumerate(improved_instructions):
                if instruction.get('type') == improvement_type and improved_text:
                    improved_instructions[i] = {**instruction, 'text': improved_text}
                    break
        
        return improved_instructions
    
    def _determine_quality_status(self, compliance_score: int, critical_issues: List[str]) -> str:
        """Determine overall quality status"""
        
        if critical_issues:
            return "NEEDS_REVISION"
        elif compliance_score >= 90:
            return "EXCELLENT"
        elif compliance_score >= 80:
            return "GOOD"
        elif compliance_score >= 70:
            return "ACCEPTABLE"
        else:
            return "NEEDS_IMPROVEMENT"
    
    def _perform_basic_quality_check(self, content: str, instructions: List[Dict]) -> Dict:
        """Perform basic quality assessment when AI processing fails"""
        
        # Basic content analysis
        word_count = len(content.split())
        has_headings = any(inst.get('type') == 'heading' for inst in instructions)
        has_proper_structure = len(instructions) > 0
        
        # Calculate basic score
        score = 70  # Base score
        if word_count > 100: score += 5
        if has_headings: score += 10
        if has_proper_structure: score += 10
        
        return {
            'score': min(score, 100),
            'content_quality': {'score': score, 'issues': ['Automated assessment only']},
            'formatting_compliance': {'score': score, 'issues': []},
            'completeness': {'score': score, 'issues': []},
            'word_count': word_count,
            'structure_elements': len(instructions)
        }
    
    def generate_quality_report(self, processing_result: ProcessingResult) -> str:
        """Generate detailed quality report"""
        
        metadata = processing_result.metadata
        compliance_score = metadata.get('compliance_score', 0)
        quality_assessment = metadata.get('quality_assessment', {})
        critical_issues = metadata.get('critical_issues', [])
        recommendations = metadata.get('recommendations', [])
        quality_status = metadata.get('quality_status', 'UNKNOWN')
        
        report = f"""
QUALITY ASSURANCE REPORT
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

OVERALL QUALITY STATUS: {quality_status}
COMPLIANCE SCORE: {compliance_score}/100

DETAILED ASSESSMENT:
"""
        
        # Add detailed quality metrics
        if quality_assessment:
            for category, details in quality_assessment.items():
                if isinstance(details, dict):
                    score = details.get('score', 0)
                    issues = details.get('issues', [])
                    report += f"\n{category.upper()}: {score}/100\n"
                    if issues:
                        for issue in issues:
                            report += f"  - {issue}\n"
        
        # Add critical issues
        if critical_issues:
            report += f"\nCRITICAL ISSUES REQUIRING ATTENTION:\n"
            for issue in critical_issues:
                report += f"  • {issue}\n"
        
        # Add recommendations
        if recommendations:
            report += f"\nRECOMMENDATIONS FOR IMPROVEMENT:\n"
            for rec in recommendations:
                report += f"  • {rec}\n"
        
        report += f"\nQUALITY AGENT NOTES:\n{processing_result.agent_notes}\n"
        
        return report


class DocumentProcessingOrchestrator:
    """Orchestrates the multi-agent document processing pipeline"""
    
    def __init__(self, standards_retriever):
        self.standards_retriever = standards_retriever
        self.content_agent = ContentStandardsAgent(standards_retriever)
        self.formatting_agent = FormattingAgent(standards_retriever)
        self.quality_agent = QualityAssuranceAgent(standards_retriever)
        
    def process_document(self, document_text: str, original_file=None, 
                        selected_agents: List[str] = None) -> Dict:
        """Run complete multi-agent processing pipeline"""
        
        if not selected_agents:
            selected_agents = ["Content Agent", "Formatting Agent", "Quality Agent"]
        
        processing_log = []
        processing_results = {}
        
        try:
            # Initialize with original document
            current_content = document_text
            current_instructions = []
            current_metadata = {}
            
            # Stage 1: Content Standards Agent
            if "Content Agent" in selected_agents:
                st.info("🖊️ Content Agent: Applying editorial standards...")
                
                content_result = self.content_agent.process({
                    'document_text': current_content
                })
                
                processing_results['content'] = content_result
                processing_log.append(f"Content Agent: {content_result.agent_notes}")
                
                if content_result.success:
                    current_content = content_result.content
                    current_instructions = content_result.instructions
                    current_metadata.update(content_result.metadata)
                    st.success(f"✅ Content processing completed - {len(content_result.metadata.get('content_changes', []))} changes made")
                else:
                    st.warning(f"⚠️ Content processing had issues: {content_result.error_message}")
            
            # Stage 2: Formatting Agent  
            if "Formatting Agent" in selected_agents:
                st.info("🎨 Formatting Agent: Applying visual standards...")
                
                formatting_result = self.formatting_agent.process({
                    'content': current_content,
                    'formatting_hints': current_instructions
                })
                
                processing_results['formatting'] = formatting_result
                processing_log.append(f"Formatting Agent: {formatting_result.agent_notes}")
                
                if formatting_result.success:
                    current_instructions = formatting_result.instructions
                    current_metadata.update(formatting_result.metadata)
                    st.success(f"✅ Formatting completed - {len(current_instructions)} structure elements created")
                else:
                    st.warning(f"⚠️ Formatting had issues: {formatting_result.error_message}")
            
            # Stage 3: Quality Assurance Agent
            if "Quality Agent" in selected_agents:
                st.info("✅ Quality Agent: Validating compliance...")
                
                quality_result = self.quality_agent.process({
                    'content': current_content,
                    'instructions': current_instructions,
                    'document_settings': current_metadata.get('document_settings', {})
                })
                
                processing_results['quality'] = quality_result
                processing_log.append(f"Quality Agent: {quality_result.agent_notes}")
                
                if quality_result.success:
                    current_instructions = quality_result.instructions  # May include improvements
                    current_metadata.update(quality_result.metadata)
                    compliance_score = quality_result.metadata.get('compliance_score', 0)
                    st.success(f"✅ Quality check completed - Compliance score: {compliance_score}/100")
                else:
                    st.warning(f"⚠️ Quality check had issues: {quality_result.error_message}")
            
            # Stage 4: Generate Final DOCX
            st.info("📄 Generating formatted DOCX...")
            
            docx_bytes = self.generate_final_docx(
                content=current_content,
                formatting_instructions=current_instructions,
                document_settings=current_metadata.get('document_settings', {}),
                original_file=original_file
            )
            
            st.success("✅ Document processing pipeline completed!")
            
            return {
                'final_docx': docx_bytes,
                'processing_log': processing_log,
                'processing_results': processing_results,
                'final_content': current_content,
                'final_instructions': current_instructions,
                'final_metadata': current_metadata,
                'pipeline_success': all(
                    result.success for result in processing_results.values()
                )
            }
            
        except Exception as e:
            error_msg = f"Pipeline orchestration error: {str(e)}"
            st.error(error_msg)
            
            # Return partial results if available
            return {
                'final_docx': None,
                'processing_log': processing_log + [f"Pipeline Error: {error_msg}"],
                'processing_results': processing_results,
                'final_content': current_content if 'current_content' in locals() else document_text,
                'final_instructions': current_instructions if 'current_instructions' in locals() else [],
                'final_metadata': current_metadata if 'current_metadata' in locals() else {},
                'pipeline_success': False,
                'error': error_msg
            }
    
    def generate_final_docx(self, content: str, formatting_instructions: List[Dict], 
                           document_settings: Dict, original_file=None) -> bytes:
        """Generate final DOCX file with all formatting applied"""
        
        try:
            # Create new document or use original as template
            if (original_file and 
                hasattr(original_file, 'type') and 
                'wordprocessingml' in str(original_file.type)):
                try:
                    # Try to use original file as template
                    original_file.seek(0)  # Reset file pointer
                    doc = Document(original_file)
                    self._clear_document_content(doc)
                    st.info("📄 Using original document as template")
                except Exception as e:
                    st.warning(f"Could not use original as template: {str(e)}")
                    doc = Document()
            else:
                doc = Document()
            
            # Apply document-level settings
            self._apply_document_settings(doc, document_settings)
            
            # Process formatting instructions
            for instruction in formatting_instructions:
                self._apply_formatting_instruction(doc, instruction)
            
            # If no instructions, create basic structure
            if not formatting_instructions:
                st.warning("No formatting instructions found - creating basic document")
                self._create_basic_document(doc, content)
            
            # Convert to bytes
            bio = io.BytesIO()
            doc.save(bio)
            bio.seek(0)
            return bio.getvalue()
            
        except Exception as e:
            st.error(f"DOCX generation error: {str(e)}")
            
            # Create minimal fallback document
            doc = Document()
            doc.add_heading('Document Processing Results', 0)
            doc.add_paragraph(f'Processing Error: {str(e)}')
            doc.add_paragraph('Original Content:')
            doc.add_paragraph(content)
            
            bio = io.BytesIO()
            doc.save(bio)
            bio.seek(0)
            return bio.getvalue()
    
    def _apply_document_settings(self, doc: Document, settings: Dict):
        """Apply document-level formatting settings"""
        
        try:
            # Set margins
            margins = settings.get('margins', {})
            for section in doc.sections:
                section.top_margin = Inches(margins.get('top', 1))
                section.bottom_margin = Inches(margins.get('bottom', 1))
                section.left_margin = Inches(margins.get('left', 1))
                section.right_margin = Inches(margins.get('right', 1))
            
            # Set default font
            style = doc.styles['Normal']
            font = style.font
            font.name = settings.get('font_family', 'Times New Roman')
            font.size = Pt(settings.get('default_font_size', 12))
            
            # Set line spacing
            paragraph_format = style.paragraph_format
            line_spacing = settings.get('line_spacing', 1.5)
            paragraph_format.line_spacing = line_spacing
            
        except Exception as e:
            st.warning(f"Document settings application error: {str(e)}")
    
    def _apply_formatting_instruction(self, doc: Document, instruction: Dict):
        """Apply individual formatting instruction to document"""
        
        try:
            element_type = instruction.get('type')
            
            if element_type == 'title':
                heading = doc.add_heading(instruction.get('text', ''), level=0)
                if instruction.get('alignment') == 'center':
                    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    
            elif element_type == 'author':
                p = doc.add_paragraph(instruction.get('text', ''))
                if instruction.get('alignment') == 'center':
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    
            elif element_type == 'heading':
                level = min(instruction.get('level', 1), 9)  # Max 9 heading levels
                text = instruction.get('text', '')
                doc.add_heading(text, level=level)
                
            elif element_type == 'paragraph':
                text = instruction.get('text', '')
                if text.strip():  # Only add non-empty paragraphs
                    p = doc.add_paragraph(text)
                    
                    # Apply alignment
                    alignment = instruction.get('alignment', 'left')
                    if alignment == 'center':
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    elif alignment == 'right':
                        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    elif alignment == 'justify':
                        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                        
            elif element_type == 'list':
                items = instruction.get('items', [])
                list_style = instruction.get('style', 'bullet')
                
                for item in items:
                    if item.strip():  # Only add non-empty items
                        if list_style == 'bullet':
                            doc.add_paragraph(item, style='List Bullet')
                        else:
                            doc.add_paragraph(item, style='List Number')
                            
            elif element_type == 'table':
                headers = instruction.get('headers', [])
                rows = instruction.get('rows', [])
                
                if headers and rows:
                    table = doc.add_table(rows=len(rows)+1, cols=len(headers))
                    table.style = 'Table Grid'
                    
                    # Add headers
                    for i, header in enumerate(headers):
                        table.cell(0, i).text = str(header)
                        
                    # Add data rows
                    for row_idx, row_data in enumerate(rows):
                        for col_idx, cell_data in enumerate(row_data):
                            if col_idx < len(headers):  # Prevent index errors
                                table.cell(row_idx+1, col_idx).text = str(cell_data)
            
            elif element_type == 'citation':
                text = instruction.get('text', '')
                if text.strip():
                    p = doc.add_paragraph(text)
                    for run in p.runs:
                        run.italic = True
                        
        except Exception as e:
            st.warning(f"Formatting instruction error for {element_type}: {str(e)}")
    
    def _clear_document_content(self, doc: Document):
        """Clear document content while preserving styles"""
        try:
            # Remove all paragraphs
            for paragraph in doc.paragraphs[:]:
                p = paragraph._element
                p.getparent().remove(p)
            
            # Remove all tables
            for table in doc.tables[:]:
                t = table._element
                t.getparent().remove(t)
                
        except Exception as e:
            st.warning(f"Document content clearing error: {str(e)}")
    
    def _create_basic_document(self, doc: Document, content: str):
        """Create basic document structure when no formatting instructions available"""
        
        doc.add_heading('Processed Document', 0)
        
        # Split content into paragraphs
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        
        for paragraph in paragraphs:
            if paragraph:
                # Simple heuristic for headings
                if len(paragraph) < 100 and paragraph.isupper():
                    doc.add_heading(paragraph, level=1)
                else:
                    doc.add_paragraph(paragraph)
    
    def generate_comprehensive_report(self, pipeline_results: Dict) -> str:
        """Generate comprehensive processing report"""
        
        processing_results = pipeline_results.get('processing_results', {})
        processing_log = pipeline_results.get('processing_log', [])
        pipeline_success = pipeline_results.get('pipeline_success', False)
        
        report = f"""
MULTI-AGENT DOCUMENT PROCESSING REPORT
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

PIPELINE STATUS: {'SUCCESS' if pipeline_success else 'PARTIAL/FAILED'}

PROCESSING PIPELINE LOG:
{chr(10).join(f"• {log}" for log in processing_log)}

AGENT PERFORMANCE SUMMARY:
"""
        
        # Add individual agent reports
        for agent_name, result in processing_results.items():
            report += f"\n{agent_name.upper()} AGENT:\n"
            report += f"  Status: {'SUCCESS' if result.success else 'FAILED'}\n"
            report += f"  Notes: {result.agent_notes}\n"
            
            if result.metadata:
                report += f"  Metadata: {json.dumps(result.metadata, indent=4)}\n"
        
        # Add quality assessment if available
        if 'quality' in processing_results:
            quality_result = processing_results['quality']
            quality_report = self.quality_agent.generate_quality_report(quality_result)
            report += f"\nDETAILED QUALITY ASSESSMENT:\n{quality_report}\n"
        
        report += f"\nPROCESSING COMPLETED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        return report


def agent_based_processing_tab():
    """New processing tab using agent architecture - REPLACE your smart_processing_tab()"""
    
    st.header("🤖 Multi-Agent Document Processing")
    
    # Initialize enhanced retriever
    if 'agent_retriever' not in st.session_state:
        st.session_state.agent_retriever = EnhancedStandardsRetriever()
    
    retriever = st.session_state.agent_retriever
    
    # Display agent status
    content_ready, format_ready, quality_ready = display_agent_status(retriever)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 📤 Upload Document for Agent Processing")
        
        uploaded_doc = st.file_uploader(
            "Choose document to process:",
            type=['pdf', 'docx', 'txt', 'png', 'jpg', 'jpeg'],
            help="Upload manuscripts, articles, reports, or any business document",
            key="agent_upload"
        )
        
        if uploaded_doc:
            st.success(f"✅ Document loaded: {uploaded_doc.name}")
            
            # Store original file for template preservation
            st.session_state.current_uploaded_file = uploaded_doc
            
            # Extract text
            if 'agent_doc_text' not in st.session_state or st.session_state.get('current_doc_name') != uploaded_doc.name:
                with st.spinner("📄 Extracting document content..."):
                    document_text = extract_text_from_document(uploaded_doc)
                    st.session_state.agent_doc_text = document_text
                    st.session_state.current_doc_name = uploaded_doc.name
            
            # Display extracted text preview
            with st.expander("📝 View Extracted Text Preview"):
                preview_text = st.session_state.agent_doc_text[:1000]
                if len(st.session_state.agent_doc_text) > 1000:
                    preview_text += "... (truncated)"
                st.text_area("Document Content Preview:", preview_text, height=200, disabled=True)
            
            # Agent Selection and Configuration
            st.markdown("### ⚙️ Agent Processing Configuration")
            
            # Agent selection with smart defaults
            available_agents = []
            if content_ready:
                available_agents.append("🖊️ Content Standards Agent")
            if format_ready:
                available_agents.append("🎨 Formatting Agent")
            if quality_ready:
                available_agents.append("✅ Quality Assurance Agent")
            
            if not available_agents:
                st.warning("⚠️ No agents available - please upload standards documents first!")
                return
            
            selected_agents = st.multiselect(
                "Select processing agents:",
                available_agents,
                default=available_agents,  # Select all available by default
                help="Choose which agents to run on your document"
            )
            
            # Processing options
            col1, col2 = st.columns(2)
            
            with col1:
                processing_mode = st.selectbox(
                    "Processing Mode:",
                    [
                        "🚀 Full Pipeline (Recommended)",
                        "🎯 Content Only",
                        "🎨 Format Only", 
                        "✅ Quality Check Only",
                        "🔧 Custom Pipeline"
                    ]
                )
            
            with col2:
                output_options = st.multiselect(
                    "Generate Outputs:",
                    ["📄 Formatted DOCX", "📊 Processing Report", "📈 Quality Report", "📝 Change Log"],
                    default=["📄 Formatted DOCX", "📊 Processing Report"]
                )
            
            # Advanced options
            with st.expander("🔧 Advanced Options"):
                col1, col2 = st.columns(2)
                
                with col1:
                    preserve_original_format = st.checkbox("Preserve Original Document Structure", value=True)
                    include_track_changes = st.checkbox("Generate Track Changes", value=True)
                
                with col2:
                    quality_threshold = st.slider("Quality Threshold", 0, 100, 80, 
                                                help="Minimum quality score for approval")
                    max_iterations = st.slider("Max Processing Iterations", 1, 3, 1)
            
            # Main processing button
            if st.button("🚀 Run Agent Pipeline", type="primary", disabled=not selected_agents):
                
                # Validate prerequisites
                if not st.session_state.standards_library:
                    st.error("❌ Please upload standards documents first in the Standards Manager tab!")
                    return
                
                if not st.session_state.standards_chunks:
                    st.warning("Building standards knowledge base...")
                    build_standards_knowledge_base()
                
                # Initialize orchestrator
                orchestrator = DocumentProcessingOrchestrator(retriever)
                
                # Map UI selections to agent names
                agent_mapping = {
                    "🖊️ Content Standards Agent": "Content Agent",
                    "🎨 Formatting Agent": "Formatting Agent", 
                    "✅ Quality Assurance Agent": "Quality Agent"
                }
                
                mapped_agents = [agent_mapping.get(agent, agent) for agent in selected_agents]
                
                # Run processing pipeline
                with st.container():
                    st.markdown("---")
                    st.subheader("🔄 Processing Pipeline")
                    
                    # Create progress tracking
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    try:
                        # Start processing
                        status_text.text("Initializing agent pipeline...")
                        progress_bar.progress(10)
                        
                        # Run the orchestrator
                        results = orchestrator.process_document(
                            st.session_state.agent_doc_text,
                            st.session_state.current_uploaded_file,
                            mapped_agents
                        )
                        
                        progress_bar.progress(100)
                        status_text.text("✅ Processing completed!")
                        
                        # Display results
                        display_agent_processing_results(results, output_options, uploaded_doc.name)
                        
                        # Save to processing history
                        save_agent_processing_result(uploaded_doc.name, results, selected_agents)
                        
                    except Exception as e:
                        progress_bar.progress(100)
                        status_text.text(f"❌ Processing failed: {str(e)}")
                        st.error(f"Pipeline error: {str(e)}")
    
    with col2:
        st.markdown("### 🧠 Agent System Info")
        
        # Agent readiness status
        if st.session_state.standards_chunks:
            st.markdown('<div class="rag-info">', unsafe_allow_html=True)
            st.write(f"**📚 Knowledge Base Status:**")
            st.write(f"• {len(st.session_state.standards_library)} standards documents")
            st.write(f"• {len(st.session_state.standards_chunks)} searchable chunks")
            st.write(f"• Ready for intelligent processing")
            
            # Show standards by type
            standards_by_type = retriever.get_standards_count_by_type()
            st.write("**📋 Available Standards:**")
            for std_type, count in standards_by_type.items():
                st.write(f"• {std_type}: {count} docs")
            
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.warning("🔄 Standards knowledge base not built")
            if st.button("🔄 Build Knowledge Base"):
                with st.spinner("Building knowledge base..."):
                    success = build_standards_knowledge_base()
                    if success:
                        st.success("✅ Knowledge base ready!")
                        st.rerun()
        
        # Quick agent preview
        if uploaded_doc and 'agent_doc_text' in st.session_state:
            st.markdown("**🔍 Quick Preview**")
            
            if content_ready and st.button("👁️ Preview Content Standards"):
                content_agent = ContentStandardsAgent(retriever)
                standards = content_agent.preview_standards(st.session_state.agent_doc_text)
                
                if standards:
                    st.write("**Relevant Content Standards:**")
                    for std in standards[:3]:
                        st.write(f"• {std['doc_name']}: {std['relevance_score']:.1f}%")
                else:
                    st.write("No relevant content standards found")
            
            if format_ready and st.button("👁️ Preview Formatting Plan"):
                formatting_agent = FormattingAgent(retriever)
                plan = formatting_agent.preview_formatting_plan(st.session_state.agent_doc_text)
                
                st.write("**Document Analysis:**")
                for key, value in plan.items():
                    st.write(f"• {key}: {value}")

def display_agent_processing_results(results: Dict, output_options: List[str], filename: str):
    """Display comprehensive agent processing results"""
    
    st.markdown("## 🎉 Agent Processing Complete!")
    
    # Pipeline status
    pipeline_success = results.get('pipeline_success', False)
    if pipeline_success:
        st.success("✅ All agents completed successfully!")
    else:
        st.warning("⚠️ Some agents encountered issues - check reports for details")
    
    # Processing statistics
    col1, col2, col3, col4 = st.columns(4)
    
    processing_results = results.get('processing_results', {})
    
    with col1:
        agents_run = len(processing_results)
        st.metric("Agents Run", agents_run)
    
    with col2:
        successful_agents = sum(1 for result in processing_results.values() if result.success)
        st.metric("Successful", successful_agents)
    
    with col3:
        # Get compliance score if available
        quality_result = processing_results.get('quality')
        compliance_score = quality_result.metadata.get('compliance_score', 0) if quality_result else 0
        st.metric("Quality Score", f"{compliance_score}/100")
    
    with col4:
        # Get word count change
        content_result = processing_results.get('content')
        original_words = content_result.metadata.get('original_word_count', 0) if content_result else 0
        edited_words = content_result.metadata.get('edited_word_count', 0) if content_result else 0
        change_pct = ((edited_words - original_words) / original_words * 100) if original_words > 0 else 0
        st.metric("Content Change", f"{change_pct:.1f}%")
    
    # Create output tabs
    tab_list = []
    if "📄 Formatted DOCX" in output_options:
        tab_list.append("📄 DOCX Output")
    if "📊 Processing Report" in output_options:
        tab_list.append("📊 Agent Reports") 
    if "📈 Quality Report" in output_options:
        tab_list.append("📈 Quality Analysis")
    if "📝 Change Log" in output_options:
        tab_list.append("📝 Change Log")
    
    if not tab_list:
        tab_list = ["📄 Results"]
    
    tabs = st.tabs(tab_list)
    tab_index = 0
    
    # DOCX Output Tab
    if "📄 Formatted DOCX" in output_options:
        with tabs[tab_index]:
            st.markdown("### 📄 Formatted Document Output")
            
            final_docx = results.get('final_docx')
            if final_docx:
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.download_button(
                        "📄 Download Formatted DOCX",
                        final_docx,
                        f"processed_{filename}",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        type="primary"
                    )
                
                with col2:
                    # Generate track changes if requested
                    if st.button("📝 Generate Track Changes"):
                        # This would need original vs final comparison
                        st.info("Track changes generation would be implemented here")
                
                with col3:
                    # Content preview
                    if st.button("👁️ Preview Content"):
                        final_content = results.get('final_content', '')
                        st.text_area("Final Content:", final_content[:1000] + "..." if len(final_content) > 1000 else final_content, height=200)
            else:
                st.error("❌ DOCX generation failed")
        
        tab_index += 1
    
    # Processing Report Tab
    if "📊 Processing Report" in output_options:
        with tabs[tab_index]:
            st.markdown("### 📊 Agent Processing Reports")
            
            # Individual agent reports
            for agent_name, result in processing_results.items():
                status_icon = "✅" if result.success else "❌"
                with st.expander(f"{status_icon} {agent_name.title()} Agent Report"):
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Status:** {'Success' if result.success else 'Failed'}")
                        st.write(f"**Agent Notes:** {result.agent_notes}")
                    
                    with col2:
                        if result.metadata:
                            st.write("**Metadata:**")
                            for key, value in result.metadata.items():
                                if isinstance(value, (int, float, str, bool)):
                                    st.write(f"• {key}: {value}")
            
            # Download comprehensive report
            orchestrator = DocumentProcessingOrchestrator(st.session_state.agent_retriever)
            comprehensive_report = orchestrator.generate_comprehensive_report(results)
            
            st.download_button(
                "📊 Download Comprehensive Report",
                comprehensive_report,
                f"agent_report_{filename.split('.')[0]}.txt",
                "text/plain"
            )
        
        tab_index += 1
    
    # Quality Analysis Tab
    if "📈 Quality Report" in output_options:
        with tabs[tab_index]:
            st.markdown("### 📈 Quality Analysis")
            
            quality_result = processing_results.get('quality')
            if quality_result:
                quality_agent = QualityAssuranceAgent(st.session_state.agent_retriever)
                quality_report = quality_agent.generate_quality_report(quality_result)
                
                st.text_area("Detailed Quality Report:", quality_report, height=400)
                
                st.download_button(
                    "📈 Download Quality Report", 
                    quality_report,
                    f"quality_report_{filename.split('.')[0]}.txt",
                    "text/plain"
                )
            else:
                st.warning("Quality analysis not performed")
        
        tab_index += 1
    
    # Change Log Tab
    if "📝 Change Log" in output_options:
        with tabs[tab_index]:
            st.markdown("### 📝 Processing Change Log")
            
            processing_log = results.get('processing_log', [])
            
            st.write("**Processing Steps:**")
            for i, log_entry in enumerate(processing_log, 1):
                st.write(f"{i}. {log_entry}")
            
            # Content changes if available
            content_result = processing_results.get('content')
            if content_result and 'content_changes' in content_result.metadata:
                st.write("**Content Changes Made:**")
                for change in content_result.metadata['content_changes']:
                    st.write(f"• {change}")

def save_agent_processing_result(filename: str, results: Dict, agents_used: List[str]):
    """Save agent processing result to history"""
    
    processing_record = {
        'filename': filename,
        'timestamp': datetime.now().isoformat(),
        'agents_used': agents_used,
        'pipeline_success': results.get('pipeline_success', False),
        'processing_log': results.get('processing_log', []),
        'agent_count': len(results.get('processing_results', {})),
        'quality_score': 0,  # Extract from quality results if available
        'processing_mode': 'Multi-Agent Pipeline'
    }
    
    # Extract quality score if available
    processing_results = results.get('processing_results', {})
    quality_result = processing_results.get('quality')
    if quality_result:
        processing_record['quality_score'] = quality_result.metadata.get('compliance_score', 0)
    
    st.session_state.processed_documents.append(processing_record)

# UPDATE YOUR MAIN FUNCTION TO USE THE NEW TAB
def main():
    """UPDATED main function - replace the tab section in your existing main()"""
    
    # ... keep your existing header and sidebar code ...
    
    # UPDATED navigation - replace your existing tab1 with agent_based_processing_tab
    tab1, tab2, tab3, tab4 = st.tabs([
        "🤖 Agent Processing",  # NEW - replaces "🎯 Smart Processing"
        "📋 Standards Manager", 
        "🔍 RAG Search", 
        "📊 Dashboard"
    ])

    with tab1:
        agent_based_processing_tab()  # NEW function instead of smart_processing_tab()
    
    with tab2:
        standards_management_tab()  # Keep existing
    
    with tab3:
        rag_search_tab()  # Keep existing
    
    with tab4:
        dashboard_tab()  # Keep existing



# 12. CRITICAL - THE APP ENTRY POINT
if __name__ == "__main__":
    main()
