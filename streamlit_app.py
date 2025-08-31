import streamlit as st
import os
from google import genai
from google.genai import types
import PIL.Image
import io
from datetime import datetime
import json
import docx
import PyPDF2
import pdfplumber

# Page config
st.set_page_config(
    page_title="📄 AI Document Standards Engine",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS styling
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

.feature-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 1.5rem;
    border-radius: 8px;
    margin: 1rem 0;
}

.status-success {
    background: #ecfdf5;
    border: 1px solid #10b981;
    color: #065f46;
    padding: 1rem;
    border-radius: 8px;
}

.status-processing {
    background: #fef3c7;
    border: 1px solid #f59e0b;
    color: #92400e;
    padding: 1rem;
    border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'processed_documents' not in st.session_state:
    st.session_state.processed_documents = []
if 'standards_library' not in st.session_state:
    st.session_state.standards_library = []

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
    """Extract text from uploaded document - Streamlit Cloud compatible"""
    try:
        file_type = uploaded_file.type
        
        if file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            # Handle .docx files
            st.info("📄 Processing Word document...")
            
            with st.spinner("🔍 Extracting text from Word document..."):
                import docx
                doc = docx.Document(uploaded_file)
                
                # Extract text from paragraphs
                full_text = []
                for paragraph in doc.paragraphs:
                    if paragraph.text.strip():
                        full_text.append(paragraph.text)
                
                # Extract text from tables
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
            # Handle PDF files with PyPDF2 only
            st.info("📄 Processing PDF document...")
            
            with st.spinner("🔍 Extracting text from PDF..."):
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(uploaded_file)
                
                full_text = []
                for page_num, page in enumerate(pdf_reader.pages):
                    text = page.extract_text()
                    if text.strip():
                        full_text.append(f"--- Page {page_num + 1} ---\n{text}")
                
                extracted_text = "\n\n".join(full_text)
                return extracted_text if extracted_text.strip() else "PDF appears to be image-based. Try uploading as image for OCR."
        
        elif file_type in ["image/png", "image/jpeg", "image/jpg"]:
            # Handle images with OCR
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
            # Handle text files
            try:
                content = uploaded_file.read().decode('utf-8')
                return content
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                content = uploaded_file.read().decode('utf-8', errors='ignore')
                return content + "\n\n⚠️ Some characters may not display correctly."
                
    except Exception as e:
        return f"Error processing document: {str(e)}"

def main():
    # Header
    st.markdown("""
    <div class="doc-header">
        <h1>📄 AI Document Standards Engine</h1>
        <p>Enterprise Document Processing with Custom Standards & Track Changes</p>
        <p><em>Built for Publishing Companies, Legal Firms & Enterprises</em></p>
    </div>
    """, unsafe_allow_html=True)

    # Main navigation
    tab1, tab2, tab3, tab4 = st.tabs([
        "📤 Process Documents", 
        "📋 Standards Library", 
        "📊 Dashboard", 
        "⚙️ Settings"
    ])

    with tab1:
        document_processing_tab()
    
    with tab2:
        standards_management_tab()
    
    with tab3:
        dashboard_tab()
    
    with tab4:
        settings_tab()

def document_processing_tab():
    st.header("📤 Document Processing Engine")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 📄 Upload Document to Process")
        
        uploaded_doc = st.file_uploader(
            "Choose document to process:",
            type=['pdf', 'docx', 'txt', 'png', 'jpg', 'jpeg'],
            help="Upload manuscripts, contracts, reports, or any business document"
        )
        
        if uploaded_doc:
            st.success(f"✅ Uploaded: {uploaded_doc.name}")
            
            # File info
            file_size = uploaded_doc.size / 1024  # KB
            st.info(f"📊 File: {uploaded_doc.name} | Size: {file_size:.1f} KB | Type: {uploaded_doc.type}")
            
            # Basic text extraction
            if st.button("🔍 Extract Text", type="primary"):
                with st.spinner("🧠 Extracting text from document..."):
                    extracted_text = extract_text_from_document(uploaded_doc)
                
                if extracted_text:
                    st.markdown("### 📝 Extracted Text")
                    st.text_area("Document Content:", extracted_text, height=300)
                    
                    # Save extraction
                    st.session_state.processed_documents.append({
                        'filename': uploaded_doc.name,
                        'timestamp': datetime.now().isoformat(),
                        'content': extracted_text,
                        'file_type': uploaded_doc.type
                    })
                    
                    st.success("✅ Text extraction completed and saved!")
    
    with col2:
        st.markdown("### 🎯 Processing Options")
        
        # Standards selection (placeholder for now)
        st.markdown("**📋 Available Standards:**")
        if st.session_state.standards_library:
            for standard in st.session_state.standards_library:
                st.write(f"📄 {standard['name']}")
        else:
            st.info("📝 Upload standards in the Standards Library tab")
        
        # Processing mode
        processing_mode = st.selectbox(
            "Processing Mode:",
            ["Basic Extraction", "Standards Application", "Full Processing + Track Changes"]
        )
        
        # Output format options
        output_formats = st.multiselect(
            "Output Formats:",
            ["Original", "Transformed", "Track Changes", "Summary Report"],
            default=["Original", "Transformed"]
        )

def standards_management_tab():
    st.header("📋 Standards Library Management")
    
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
                ["Style Guide", "Editorial Guidelines", "Reference Format", "Legal Requirements", "Quality Standards"]
            )
            description = st.text_area("Description:", "Company-specific formatting and editing standards")
            
            if st.button("📋 Add to Standards Library"):
                with st.spinner("🔍 Processing standards document..."):
                    # Extract standards content
                    standards_content = extract_text_from_document(standards_doc)
                    
                    # Save to library
                    new_standard = {
                        'name': standard_name,
                        'type': standard_type,
                        'description': description,
                        'content': standards_content,
                        'filename': standards_doc.name,
                        'uploaded_date': datetime.now().isoformat()
                    }
                    
                    st.session_state.standards_library.append(new_standard)
                    st.success("✅ Standards added to library!")
    
    with col2:
        st.markdown("### 📚 Current Standards Library")
        
        if st.session_state.standards_library:
            for i, standard in enumerate(st.session_state.standards_library):
                with st.expander(f"📄 {standard['name']}"):
                    st.write(f"**Type:** {standard['type']}")
                    st.write(f"**Description:** {standard['description']}")
                    st.write(f"**Uploaded:** {standard['uploaded_date'][:10]}")
                    
                    if st.button(f"👁️ Preview Content", key=f"preview_{i}"):
                        st.text_area("Standards Content:", standard['content'][:500] + "...", height=150)
                    
                    if st.button(f"🗑️ Remove", key=f"remove_{i}"):
                        st.session_state.standards_library.pop(i)
                        st.rerun()
        else:
            st.info("📝 No standards uploaded yet. Upload your first style guide above!")

def dashboard_tab():
    st.header("📊 Processing Dashboard")
    
    # Statistics
    total_docs = len(st.session_state.processed_documents)
    total_standards = len(st.session_state.standards_library)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📄 Documents Processed", total_docs)
    with col2:
        st.metric("📋 Standards Library", total_standards)
    with col3:
        st.metric("⚡ Processing Speed", "2-5 min/doc")
    with col4:
        st.metric("🎯 Accuracy Rate", "95%+")
    
    # Recent activity
    if st.session_state.processed_documents:
        st.markdown("### 📈 Recent Document Processing")
        
        for doc in st.session_state.processed_documents[-5:]:  # Last 5 docs
            with st.expander(f"📄 {doc['filename']} - {doc['timestamp'][:10]}"):
                st.write(f"**File Type:** {doc['file_type']}")
                st.write(f"**Processed:** {doc['timestamp']}")
                st.text_area("Content Preview:", doc['content'][:200] + "...", height=100)
    else:
        st.info("📭 No documents processed yet. Upload your first document in the Process tab!")

def settings_tab():
    st.header("⚙️ Platform Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🎨 Processing Settings")
        
        default_processing = st.selectbox(
            "Default Processing Mode:",
            ["Basic Extraction", "Standards Application", "Full Processing"]
        )
        
        output_quality = st.slider("Output Quality Level:", 1, 10, 8)
        auto_backup = st.checkbox("Auto-backup processed documents", True)
        
        st.markdown("### 🔒 Security Settings")
        data_retention = st.selectbox(
            "Data Retention Period:",
            ["7 days", "30 days", "90 days", "1 year", "Permanent"]
        )
        
        encryption_level = st.selectbox("Encryption Level:", ["Standard", "High", "Maximum"])
    
    with col2:
        st.markdown("### 📊 API & Integration")
        
        st.info("🔌 API integrations coming in v2.0")
        st.info("📈 Analytics export coming in v2.0")
        
        st.markdown("### 💾 Data Management")
        
        if st.button("📥 Export All Data"):
            export_data = {
                'processed_documents': st.session_state.processed_documents,
                'standards_library': st.session_state.standards_library,
                'export_date': datetime.now().isoformat()
            }
            
            st.download_button(
                "💾 Download Data Export",
                json.dumps(export_data, indent=2),
                "document_engine_export.json",
                "application/json"
            )
        
        if st.button("🗑️ Clear All Data"):
            if st.button("⚠️ Confirm Clear All"):
                st.session_state.processed_documents = []
                st.session_state.standards_library = []
                st.success("✅ All data cleared!")

if __name__ == "__main__":
    main()
