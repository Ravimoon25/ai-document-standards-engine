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

# Page config
st.set_page_config(
    page_title="📄 AI Document Standards Engine",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Enhanced CSS for document processing
st.markdown("""
<style>
.main .block-container {
    padding: 1rem;
    max-width: 100%;
}

.doc-header {
    background: linear-gradient(135deg, #1e3a8a 0%, #3730a3 100%);
    color: white;
    padding: 2rem;
    border-radius: 12px;
    text-align: center;
    margin-bottom: 2rem;
}

.standards-card {
    background: #f0f9ff;
    border: 2px solid #0ea5e9;
    padding: 1.5rem;
    border-radius: 8px;
    margin: 1rem 0;
}

.processing-card {
    background: #fef3c7;
    border: 1px solid #f59e0b;
    padding: 1rem;
    border-radius: 8px;
    margin: 0.5rem 0;
}

.result-card {
    background: #ecfdf5;
    border: 1px solid #10b981;
    padding: 1.5rem;
    border-radius: 8px;
    margin: 1rem 0;
}

.change-highlight {
    background: #fef2f2;
    border-left: 4px solid #ef4444;
    padding: 0.5rem;
    margin: 0.5rem 0;
}

.rag-info {
    background: #f3f4f6;
    border: 1px solid #9ca3af;
    padding: 1rem;
    border-radius: 6px;
    font-size: 0.9rem;
}
</style>
""", unsafe_allow_html=True)

# Initialize session state
def init_session_state():
    if 'processed_documents' not in st.session_state:
        st.session_state.processed_documents = []
    if 'standards_library' not in st.session_state:
        st.session_state.standards_library = []
    if 'standards_chunks' not in st.session_state:
        st.session_state.standards_chunks = []
    if 'vectorizer' not in st.session_state:
        st.session_state.vectorizer = None
    if 'chunk_embeddings' not in st.session_state:
        st.session_state.chunk_embeddings = None

init_session_state()

@st.cache_resource
def get_client():
    """Initialize Gemini client"""
    try:
        api_key = st.secrets["GOOGLE_API_KEY"]
        return genai.Client(api_key=api_key)
    except Exception as e:
        st.error(f"Failed to initialize AI client: {str(e)}")
        st.stop()

def extract_text_from_document(uploaded_file):
    """Extract text from uploaded document - production ready"""
    try:
        file_type = uploaded_file.type
        
        if file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            st.info("📄 Processing Word document...")
            
            with st.spinner("🔍 Extracting text from Word document..."):
                doc = docx.Document(uploaded_file)
                
                full_text = []
                for paragraph in doc.paragraphs:
                    if paragraph.text.strip():
                        full_text.append(paragraph.text)
                
                for table in doc.tables:
                    for row in table.rows:
                        row_text = []
                        for cell in row.cells:
                            if cell.text.strip():
                                row_text.append(cell.text.strip())
                        if row_text:
                            full_text.append(" | ".join(row_text))
                
                extracted_text = "\n".join(full_text)
                return extracted_text if extracted_text.strip() else "No text found in Word document."
        
        elif file_type == "application/pdf":
            st.info("📄 Processing PDF document...")
            
            with st.spinner("🔍 Extracting text from PDF..."):
                pdf_reader = PyPDF2.PdfReader(uploaded_file)
                
                full_text = []
                for page_num, page in enumerate(pdf_reader.pages):
                    text = page.extract_text()
                    if text.strip():
                        full_text.append(f"--- Page {page_num + 1} ---\n{text}")
                
                extracted_text = "\n\n".join(full_text)
                return extracted_text if extracted_text.strip() else "PDF appears to be image-based. Try uploading as image for OCR."
        
        elif file_type in ["image/png", "image/jpeg", "image/jpg"]:
            st.info("🖼️ Processing image with OCR...")
            
            image = PIL.Image.open(uploaded_file)
            
            with st.spinner("🔍 Extracting text from image..."):
                client = get_client()
                response = client.models.generate_content(
                    model="gemini-2.5-flash-image-preview",
                    contents=["Extract all text from this document image, maintaining formatting and structure:", image]
                )
                
                extracted_text = ""
                for part in response.parts:
                    if part.text:
                        extracted_text += part.text
                
                return extracted_text if extracted_text.strip() else "No text detected in image."
        
        else:
            try:
                content = uploaded_file.read().decode('utf-8')
                return content
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                content = uploaded_file.read().decode('utf-8', errors='ignore')
                return content + "\n\n⚠️ Some characters may not display correctly."
                
    except Exception as e:
        return f"Error processing document: {str(e)}"

class StandardsProcessor:
    """RAG system for processing and retrieving standards"""
    
    def __init__(self):
        self.chunk_size = 500  # words per chunk
        self.overlap = 50      # word overlap between chunks
    
    def chunk_document(self, text: str, doc_name: str) -> List[Dict]:
        """Split large standards document into searchable chunks"""
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), self.chunk_size - self.overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = " ".join(chunk_words)
            
            # Extract section information if available
            section_match = re.search(r'(#+\s*.+|\d+\.\d*\s*.+|Section\s+\d+)', chunk_text)
            section = section_match.group(1) if section_match else f"Chunk {len(chunks) + 1}"
            
            chunks.append({
                'text': chunk_text,
                'section': section,
                'doc_name': doc_name,
                'chunk_id': f"{doc_name}_chunk_{len(chunks)}",
                'word_count': len(chunk_words)
            })
        
        return chunks
    
    def create_embeddings(self, chunks: List[Dict]) -> Tuple[TfidfVectorizer, np.ndarray]:
        """Create TF-IDF embeddings for semantic search"""
        chunk_texts = [chunk['text'] for chunk in chunks]
        
        vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2),  # Include bigrams for better context
            min_df=1,
            max_df=0.95
        )
        
        embeddings = vectorizer.fit_transform(chunk_texts)
        return vectorizer, embeddings.toarray()
    
    def semantic_search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Find most relevant standards chunks for a query"""
        if not st.session_state.vectorizer or st.session_state.chunk_embeddings is None:
            return []
        
        # Transform query using existing vectorizer
        query_vector = st.session_state.vectorizer.transform([query])
        
        # Calculate similarities
        similarities = cosine_similarity(query_vector, st.session_state.chunk_embeddings)[0]
        
        # Get top-k most similar chunks
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            if similarities[idx] > 0.1:  # Minimum similarity threshold
                chunk = st.session_state.standards_chunks[idx]
                results.append({
                    **chunk,
                    'similarity': similarities[idx],
                    'relevance_score': similarities[idx] * 100
                })
        
        return results

def build_standards_knowledge_base():
    """Build RAG knowledge base from all uploaded standards"""
    if not st.session_state.standards_library:
        return False
    
    processor = StandardsProcessor()
    all_chunks = []
    
    # Process all standards documents
    for standard in st.session_state.standards_library:
        chunks = processor.chunk_document(standard['content'], standard['name'])
        all_chunks.extend(chunks)
    
    if all_chunks:
        # Create embeddings
        vectorizer, embeddings = processor.create_embeddings(all_chunks)
        
        # Store in session state
        st.session_state.standards_chunks = all_chunks
        st.session_state.vectorizer = vectorizer
        st.session_state.chunk_embeddings = embeddings
        
        return True
    
    return False

def apply_standards_to_document(document_text: str, standards_context: List[Dict]) -> str:
    """Apply retrieved standards to document using AI"""
    try:
        client = get_client()
        
        # Prepare context from retrieved standards
        context_text = "\n\n".join([
            f"STANDARD RULE (from {chunk['doc_name']}, {chunk['section']}):\n{chunk['text']}"
            for chunk in standards_context
        ])
        
        prompt = f"""
        You are an expert editor for a medical journal publishing company. Apply the provided editorial standards to improve this document.

        EDITORIAL STANDARDS TO APPLY:
        {context_text}

        DOCUMENT TO EDIT:
        {document_text}

        INSTRUCTIONS:
        1. Apply ALL relevant standards from the provided guidelines
        2. Fix formatting, citation styles, and structural issues
        3. Improve language and clarity while maintaining academic tone
        4. Ensure compliance with technical specifications
        5. Maintain the original meaning and content
        6. Focus on professional publishing standards

        PROVIDE:
        1. The edited document with all improvements applied
        2. A summary of changes made
        3. List of standards applied

        Format your response as:
        EDITED_DOCUMENT:
        [Provide the fully edited document here]

        CHANGES_SUMMARY:
        [List all changes made and why]

        STANDARDS_APPLIED:
        [List which specific standards were applied]
        """
        
        response = client.models.generate_content(
            model="gemini-2.5-flash-image-preview",
            contents=prompt
        )
        
        result = ""
        for part in response.parts:
            if part.text:
                result += part.text
        
        return result
        
    except Exception as e:
        return f"Error applying standards: {str(e)}"

def generate_track_changes_document(original: str, edited: str) -> str:
    """Generate professional track changes document"""
    try:
        client = get_client()
        
        prompt = f"""
        Create a professional track changes document showing all modifications between the original and edited versions.

        ORIGINAL DOCUMENT:
        {original}

        EDITED DOCUMENT:
        {edited}

        INSTRUCTIONS:
        1. Identify all changes between original and edited versions
        2. Format as professional track changes with:
           - [DELETED: original text] for removals
           - [ADDED: new text] for additions
           - [CHANGED: old text → new text] for modifications
        3. Add comments explaining the reason for each change
        4. Include line numbers or section references
        5. Provide change statistics summary

        FORMAT:
        TRACK_CHANGES_DOCUMENT:
        [Document with all changes marked]

        CHANGE_STATISTICS:
        - Total Changes: X
        - Additions: X
        - Deletions: X
        - Modifications: X
        
        CHANGE_SUMMARY:
        [Brief summary of major changes made]
        """
        
        response = client.models.generate_content(
            model="gemini-2.5-flash-image-preview",
            contents=prompt
        )
        
        result = ""
        for part in response.parts:
            if part.text:
                result += part.text
        
        return result
        
    except Exception as e:
        return f"Error generating track changes: {str(e)}"

def main():
    # Header
    st.markdown("""
    <div class="doc-header">
        <h1>📄 AI Document Standards Engine</h1>
        <p>Enterprise Document Processing with RAG-Powered Standards Application</p>
        <p><em>Intelligent Standards • Track Changes • Professional Editing</em></p>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar RAG status
    with st.sidebar:
        st.title("🧠 RAG System Status")
        
        # Standards library status
        num_standards = len(st.session_state.standards_library)
        num_chunks = len(st.session_state.standards_chunks)
        
        if num_standards > 0:
            st.success(f"✅ {num_standards} standards loaded")
            st.info(f"📚 {num_chunks} searchable chunks")
            
            if st.button("🔄 Rebuild Knowledge Base"):
                with st.spinner("🧠 Building RAG knowledge base..."):
                    success = build_standards_knowledge_base()
                    if success:
                        st.success("✅ Knowledge base updated!")
                        st.rerun()
        else:
            st.warning("📋 No standards uploaded yet")
        
        st.markdown("---")
        
        # Processing stats
        st.markdown("**📊 Processing Stats**")
        st.metric("Documents Processed", len(st.session_state.processed_documents))
        st.metric("Standards Library", num_standards)

    # Main navigation
    tab1, tab2, tab3, tab4 = st.tabs([
        "🎯 Smart Processing", 
        "📋 Standards Manager", 
        "🔍 RAG Search", 
        "📊 Dashboard"
    ])

    with tab1:
        smart_processing_tab()
    
    with tab2:
        standards_management_tab()
    
    with tab3:
        rag_search_tab()
    
    with tab4:
        dashboard_tab()

def smart_processing_tab():
    st.header("🎯 Intelligent Document Processing")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 📤 Upload Document for Standards Application")
        
        uploaded_doc = st.file_uploader(
            "Choose document to process:",
            type=['pdf', 'docx', 'txt', 'png', 'jpg', 'jpeg'],
            help="Upload manuscripts, articles, reports, or any business document"
        )
        
        if uploaded_doc:
            st.success(f"✅ Document loaded: {uploaded_doc.name}")
            
            # Extract text first
            if 'current_doc_text' not in st.session_state:
                with st.spinner("📄 Extracting document content..."):
                    document_text = extract_text_from_document(uploaded_doc)
                    st.session_state.current_doc_text = document_text
            
            # Display extracted text
            with st.expander("📝 View Extracted Text"):
                st.text_area("Document Content:", st.session_state.current_doc_text, height=200)
            
            # Processing options
            st.markdown("### ⚙️ Processing Configuration")
            
            processing_mode = st.selectbox(
                "Processing Mode:",
                [
                    "🧠 Smart Standards Application (RAG)",
                    "📋 Apply All Standards", 
                    "🔍 Analysis Only",
                    "✏️ Custom Editing Rules"
                ]
            )
            
            if processing_mode == "✏️ Custom Editing Rules":
                custom_rules = st.text_area(
                    "Custom Editing Instructions:",
                    "Apply academic writing standards, improve clarity, fix citation format",
                    height=100
                )
            
            # Output options
            st.markdown("### 📑 Output Format Options")
            output_options = st.multiselect(
                "Generate:",
                ["📄 Original Document", "✨ Transformed Document", "📝 Track Changes", "📊 Analysis Report"],
                default=["📄 Original Document", "✨ Transformed Document", "📝 Track Changes"]
            )
            
            # Main processing button
            if st.button("🚀 Process Document", type="primary"):
                if st.session_state.standards_library:
                    
                    # Build knowledge base if not exists
                    if not st.session_state.standards_chunks:
                        with st.spinner("🧠 Building standards knowledge base..."):
                            build_standards_knowledge_base()
                    
                    # Smart processing with RAG
                    if processing_mode == "🧠 Smart Standards Application (RAG)":
                        with st.spinner("🔍 Finding relevant standards..."):
                            processor = StandardsProcessor()
                            relevant_standards = processor.semantic_search(
                                st.session_state.current_doc_text[:1000],  # Use first 1000 chars for search
                                top_k=8
                            )
                        
                        if relevant_standards:
                            st.markdown("### 🎯 Retrieved Standards")
                            for i, standard in enumerate(relevant_standards):
                                with st.expander(f"📋 Rule {i+1} - {standard['section']} (Relevance: {standard['relevance_score']:.1f}%)"):
                                    st.write(f"**From:** {standard['doc_name']}")
                                    st.write(f"**Section:** {standard['section']}")
                                    st.text_area("Rule Content:", standard['text'], height=100, key=f"rule_{i}")
                            
                            # Apply standards
                            with st.spinner("✨ Applying standards to document..."):
                                edited_result = apply_standards_to_document(
                                    st.session_state.current_doc_text, 
                                    relevant_standards
                                )
                            
                            # Process results
                            if edited_result:
                                # Parse the AI response
                                sections = edited_result.split("EDITED_DOCUMENT:")
                                if len(sections) > 1:
                                    edited_content = sections[1].split("CHANGES_SUMMARY:")[0].strip()
                                    
                                    # Display results based on selected options
                                    display_processing_results(
                                        st.session_state.current_doc_text,
                                        edited_content,
                                        edited_result,
                                        output_options
                                    )
                                    
                                    # Save to history
                                    save_processing_result(uploaded_doc.name, edited_result, relevant_standards)
                                else:
                                    st.error("❌ Failed to parse editing results")
                        else:
                            st.warning("⚠️ No relevant standards found for this document type")
                
                else:
                    st.warning("⚠️ Please upload standards documents first in the Standards Manager tab!")
    
    with col2:
        st.markdown("### 🧠 RAG System Info")
        
        if st.session_state.standards_chunks:
            st.markdown('<div class="rag-info">', unsafe_allow_html=True)
            st.write(f"**📚 Knowledge Base Status:**")
            st.write(f"• {len(st.session_state.standards_library)} standards documents")
            st.write(f"• {len(st.session_state.standards_chunks)} searchable chunks")
            st.write(f"• {st.session_state.chunk_embeddings.shape[1] if st.session_state.chunk_embeddings is not None else 0} embedding dimensions")
            st.write(f"• Ready for intelligent retrieval")
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="rag-info">', unsafe_allow_html=True)
            st.write("**🔄 RAG System Setup:**")
            st.write("1. Upload standards documents")
            st.write("2. System automatically chunks content")
            st.write("3. Creates semantic embeddings")
            st.write("4. Enables intelligent retrieval")
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Quick standards preview
        if st.session_state.standards_library:
            st.markdown("**📋 Available Standards:**")
            for standard in st.session_state.standards_library:
                st.write(f"• {standard['name']}")

def display_processing_results(original: str, edited: str, full_result: str, options: List[str]):
    """Display processing results based on selected options"""
    
    st.markdown("## 🎉 Processing Complete!")
    
    # Create tabs for different outputs
    result_tabs = []
    if "📄 Original Document" in options:
        result_tabs.append("📄 Original")
    if "✨ Transformed Document" in options:
        result_tabs.append("✨ Transformed") 
    if "📝 Track Changes" in options:
        result_tabs.append("📝 Track Changes")
    if "📊 Analysis Report" in options:
        result_tabs.append("📊 Analysis")
    
    tabs = st.tabs(result_tabs)
    
    tab_index = 0
    
    if "📄 Original Document" in options:
        with tabs[tab_index]:
            st.markdown("### 📄 Original Document")
            st.text_area("Original Content:", original, height=400)
            
            # Download original
            st.download_button(
                "💾 Download Original",
                original,
                "original_document.txt",
                "text/plain"
            )
        tab_index += 1
    
    if "✨ Transformed Document" in options:
        with tabs[tab_index]:
            st.markdown("### ✨ Standards-Applied Document")
            st.text_area("Edited Content:", edited, height=400)
            
            # Download edited
            st.download_button(
                "💾 Download Edited",
                edited,
                "edited_document.txt",
                "text/plain"
            )
        tab_index += 1
    
    if "📝 Track Changes" in options:
        with tabs[tab_index]:
            st.markdown("### 📝 Professional Track Changes")
            
            with st.spinner("📝 Generating track changes document..."):
                track_changes = generate_track_changes_document(original, edited)
            
            st.text_area("Track Changes:", track_changes, height=400)
            
            # Download track changes
            st.download_button(
                "💾 Download Track Changes",
                track_changes,
                "track_changes_document.txt",
                "text/plain"
            )
        tab_index += 1
    
    if "📊 Analysis Report" in options:
        with tabs[tab_index]:
            st.markdown("### 📊 Processing Analysis Report")
            
            # Extract analysis from full result
            if "CHANGES_SUMMARY:" in full_result:
                changes_section = full_result.split("CHANGES_SUMMARY:")[1].split("STANDARDS_APPLIED:")[0]
                standards_section = full_result.split("STANDARDS_APPLIED:")[1] if "STANDARDS_APPLIED:" in full_result else ""
                
                st.markdown("**📝 Changes Made:**")
                st.write(changes_section)
                
                st.markdown("**📋 Standards Applied:**")
                st.write(standards_section)
            
            # Processing metrics
            original_words = len(original.split())
            edited_words = len(edited.split())
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Original Words", original_words)
            with col2:
                st.metric("Edited Words", edited_words)
            with col3:
                change_percent = ((edited_words - original_words) / original_words * 100) if original_words > 0 else 0
                st.metric("Change %", f"{change_percent:.1f}%")

def standards_management_tab():
    st.header("📋 Enterprise Standards Library")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("### 📤 Upload Standards Documents")
        
        standards_doc = st.file_uploader(
            "Upload style guides, editorial standards:",
            type=['pdf', 'docx', 'txt'],
            help="Upload company style guides, formatting rules, editorial guidelines",
            key="standards_upload"
        )
        
        if standards_doc:
            st.success(f"✅ Standards document: {standards_doc.name}")
            
            # Standards metadata
            standard_name = st.text_input("Standard Name:", standards_doc.name.split('.')[0])
            standard_type = st.selectbox(
                "Standard Type:",
                ["Style Guide", "Editorial Guidelines", "Reference Format", "Figure Standards", "Legal Requirements", "Quality Standards"]
            )
            description = st.text_area("Description:", "Enterprise formatting and editing standards")
            priority = st.selectbox("Priority Level:", ["High", "Medium", "Low"])
            
            if st.button("📚 Add to Standards Library"):
                with st.spinner("🔍 Processing standards document..."):
                    standards_content = extract_text_from_document(standards_doc)
                    
                    if standards_content and len(standards_content.strip()) > 100:
                        # Save to library
                        new_standard = {
                            'name': standard_name,
                            'type': standard_type,
                            'description': description,
                            'priority': priority,
                            'content': standards_content,
                            'filename': standards_doc.name,
                            'uploaded_date': datetime.now().isoformat(),
                            'word_count': len(standards_content.split())
                        }
                        
                        st.session_state.standards_library.append(new_standard)
                        
                        # Rebuild RAG knowledge base
                        build_standards_knowledge_base()
                        
                        st.success("✅ Standards added and knowledge base updated!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to extract content from standards document")
    
    with col2:
        st.markdown("### 📚 Current Standards Library")
        
        if st.session_state.standards_library:
            for i, standard in enumerate(st.session_state.standards_library):
                with st.expander(f"📄 {standard['name']} ({standard['type']})"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Type:** {standard['type']}")
                        st.write(f"**Priority:** {standard['priority']}")
                        st.write(f"**Word Count:** {standard['word_count']:,}")
                    
                    with col2:
                        st.write(f"**Uploaded:** {standard['uploaded_date'][:10]}")
                        st.write(f"**File:** {standard['filename']}")
                    
                    st.write(f"**Description:** {standard['description']}")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button(f"👁️ Preview", key=f"preview_{i}"):
                            st.text_area("Content Preview:", standard['content'][:800] + "...", height=200)
                    
                    with col2:
                        if st.button(f"📥 Download", key=f"download_{i}"):
                            st.download_button(
                                "Download Standards",
                                standard['content'],
                                f"{standard['name']}.txt",
                                "text/plain",
                                key=f"dl_{i}"
                            )
                    
                    with col3:
                        if st.button(f"🗑️ Remove", key=f"remove_{i}"):
                            st.session_state.standards_library.pop(i)
                            build_standards_knowledge_base()  # Rebuild after removal
                            st.rerun()
        else:
            st.markdown('<div class="standards-card">', unsafe_allow_html=True)
            st.markdown("**📚 No Standards Yet**")
            st.write("Upload your first style guide or editorial standards document above.")
            st.write("The system will automatically:")
            st.write("• Extract and chunk the content")
            st.write("• Create semantic embeddings")
            st.write("• Enable intelligent retrieval")
            st.markdown('</div>', unsafe_allow_html=True)

def rag_search_tab():
    st.header("🔍 RAG System - Standards Search")
    
    if not st.session_state.standards_chunks:
        st.warning("📚 Please upload standards documents first to enable RAG search!")
        return
    
    st.markdown("### 🔍 Search Your Standards Library")
    
    # Search interface
    search_query = st.text_area(
        "Search for specific standards or rules:",
        "citation format requirements for journal articles",
        height=100,
        help="Describe what standards you're looking for - the RAG system will find relevant rules"
    )
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        num_results = st.slider("Number of results:", 3, 15, 8)
        
    with col2:
        if st.button("🔍 Search Standards", type="primary"):
            if search_query.strip():
                processor = StandardsProcessor()
                
                with st.spinner("🧠 Searching knowledge base..."):
                    results = processor.semantic_search(search_query, top_k=num_results)
                
                if results:
                    st.markdown(f"### 📊 Found {len(results)} Relevant Standards")
                    
                    for i, result in enumerate(results):
                        relevance_color = "🟢" if result['relevance_score'] > 70 else "🟡" if result['relevance_score'] > 40 else "🔴"
                        
                        with st.expander(f"{relevance_color} **Rule {i+1}** - {result['section']} (Relevance: {result['relevance_score']:.1f}%)"):
                            col1, col2 = st.columns([2, 1])
                            
                            with col1:
                                st.markdown(f"**📄 Document:** {result['doc_name']}")
                                st.markdown(f"**📍 Section:** {result['section']}")
                                st.markdown(f"**🎯 Relevance:** {result['relevance_score']:.1f}%")
                                
                            with col2:
                                st.markdown(f"**📊 Words:** {result['word_count']}")
                                st.markdown(f"**🔗 Chunk ID:** {result['chunk_id']}")
                            
                            st.markdown("**📝 Content:**")
                            st.text_area("Rule Content:", result['text'], height=150, key=f"search_result_{i}")
                            
                            if st.button(f"📋 Apply This Rule", key=f"apply_rule_{i}"):
                                st.info(f"Rule from {result['doc_name']} ready to apply!")
                else:
                    st.info("🔍 No relevant standards found. Try different search terms or upload more comprehensive standards.")
            else:
                st.warning("⚠️ Please enter a search query!")
    
    # RAG System Analytics
    st.markdown("---")
    st.markdown("### 📊 RAG System Analytics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📚 Standards Docs", len(st.session_state.standards_library))
    
    with col2:
        st.metric("🧩 Total Chunks", len(st.session_state.standards_chunks))
    
    with col3:
        avg_chunk_size = np.mean([chunk['word_count'] for chunk in st.session_state.standards_chunks]) if st.session_state.standards_chunks else 0
        st.metric("📏 Avg Chunk Size", f"{avg_chunk_size:.0f} words")
    
    with col4:
        vocab_size = st.session_state.vectorizer.vocabulary_.__len__() if st.session_state.vectorizer else 0
        st.metric("🔤 Vocabulary Size", vocab_size)
    
    # Knowledge base overview
    if st.session_state.standards_chunks:
        st.markdown("### 🗂️ Knowledge Base Overview")
        
        # Group chunks by document
        doc_chunks = {}
        for chunk in st.session_state.standards_chunks:
            doc_name = chunk['doc_name']
            if doc_name not in doc_chunks:
                doc_chunks[doc_name] = []
            doc_chunks[doc_name].append(chunk)
        
        for doc_name, chunks in doc_chunks.items():
            with st.expander(f"📄 {doc_name} ({len(chunks)} chunks)"):
                total_words = sum(chunk['word_count'] for chunk in chunks)
                st.write(f"**Total Words:** {total_words:,}")
                st.write(f"**Chunks:** {len(chunks)}")
                st.write(f"**Average Chunk Size:** {total_words/len(chunks):.0f} words")
                
                # Sample chunks
                st.write("**Sample Sections:**")
                for chunk in chunks[:3]:
                    st.write(f"• {chunk['section']}")

def dashboard_tab():
    st.header("📊 Processing Dashboard & Analytics")
    
    # Overall metrics
    total_docs = len(st.session_state.processed_documents)
    total_standards = len(st.session_state.standards_library)
    total_chunks = len(st.session_state.standards_chunks)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📄 Documents Processed", total_docs)
    with col2:
        st.metric("📚 Standards Library", total_standards)
    with col3:
        st.metric("🧩 Knowledge Chunks", total_chunks)
    with col4:
        processing_rate = "2-5 min" if total_standards > 0 else "Setup Required"
        st.metric("⚡ Processing Speed", processing_rate)
    
    # System health
    st.markdown("### 🏥 System Health")
    
    health_items = [
        ("RAG System", "🟢 Active" if st.session_state.standards_chunks else "🔴 Inactive"),
        ("Vector Embeddings", "🟢 Ready" if st.session_state.chunk_embeddings is not None else "🔴 Not Built"),
        ("Standards Library", "🟢 Loaded" if total_standards > 0 else "🟡 Empty"),
        ("Processing Engine", "🟢 Online")
    ]
    
    for item, status in health_items:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**{item}:**")
        with col2:
            st.write(status)
    
    # Recent activity
    if st.session_state.processed_documents:
        st.markdown("### 📈 Recent Document Processing")
        
        for i, doc in enumerate(st.session_state.processed_documents[-5:]):
            with st.expander(f"📄 {doc['filename']} - {doc['timestamp'][:10]}"):
                st.write(f"**Processed:** {doc['timestamp']}")
                st.write(f"**File Type:** {doc.get('file_type', 'Unknown')}")
                if 'standards_applied' in doc:
                    st.write(f"**Standards Applied:** {len(doc['standards_applied'])}")
                
                # Content preview
                content_preview = doc.get('content', '')[:300] + "..." if 'content' in doc else "No content preview"
                st.text_area("Content Preview:", content_preview, height=100, key=f"preview_{i}")
    else:
        st.info("📭 No documents processed yet. Upload your first document in the Smart Processing tab!")
    
    # Standards library analysis
    if st.session_state.standards_library:
        st.markdown("### 📚 Standards Library Analysis")
        
        # Standards by type
        type_counts = {}
        total_words = 0
        
        for standard in st.session_state.standards_library:
            std_type = standard['type']
            type_counts[std_type] = type_counts.get(std_type, 0) + 1
            total_words += standard.get('word_count', 0)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📊 Standards by Type:**")
            for std_type, count in type_counts.items():
                st.write(f"• {std_type}: {count}")
        
        with col2:
            st.metric("📝 Total Words", f"{total_words:,}")
            st.metric("📊 Average Doc Size", f"{total_words//len(st.session_state.standards_library):,} words")
    
    # Export and backup options
    st.markdown("### 💾 Data Management")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Export Processing Report"):
            report_data = {
                'summary': {
                    'documents_processed': total_docs,
                    'standards_loaded': total_standards,
                    'knowledge_chunks': total_chunks,
                    'export_date': datetime.now().isoformat()
                },
                'processed_documents': st.session_state.processed_documents,
                'standards_library': [
                    {k: v for k, v in std.items() if k != 'content'}  # Exclude content for size
                    for std in st.session_state.standards_library
                ]
            }
            
            st.download_button(
                "📥 Download Report",
                json.dumps(report_data, indent=2),
                "processing_report.json",
                "application/json"
            )
    
    with col2:
        if st.button("🗂️ Export Standards List"):
            if st.session_state.standards_library:
                standards_summary = []
                for std in st.session_state.standards_library:
                    standards_summary.append({
                        'name': std['name'],
                        'type': std['type'],
                        'word_count': std.get('word_count', 0),
                        'upload_date': std['uploaded_date']
                    })
                
                df = pd.DataFrame(standards_summary)
                csv_data = df.to_csv(index=False)
                
                st.download_button(
                    "📥 Download CSV",
                    csv_data,
                    "standards_library.csv",
                    "text/csv"
                )
            else:
                st.warning("No standards to export")
    
    with col3:
        if st.button("🧹 Clear All Data"):
            if st.button("⚠️ Confirm Delete All", key="confirm_delete"):
                st.session_state.processed_documents = []
                st.session_state.standards_library = []
                st.session_state.standards_chunks = []
                st.session_state.vectorizer = None
                st.session_state.chunk_embeddings = None
                st.success("✅ All data cleared!")
                st.rerun()

def save_processing_result(filename: str, result: str, standards_used: List[Dict]):
    """Save processing result to history"""
    processing_record = {
        'filename': filename,
        'timestamp': datetime.now().isoformat(),
        'result': result,
        'standards_applied': len(standards_used),
        'standards_used': [s['doc_name'] for s in standards_used],
        'processing_mode': 'RAG Smart Processing'
    }
    
    st.session_state.processed_documents.append(processing_record)

if __name__ == "__main__":
    main()
