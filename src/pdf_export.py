import subprocess
import os

def export_to_pdf(docx_path: str, output_dir: str) -> str:
    """
    Exports a docx file to PDF using LibreOffice in headless mode.
    Returns the path to the generated PDF.
    Raises an Exception if the conversion fails.
    """
    if not os.path.exists(docx_path):
        raise FileNotFoundError(f"Input docx not found: {docx_path}")
        
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        
    # Standard LibreOffice installation path on Windows
    soffice_path = r"C:\Program Files\LibreOffice\program\soffice.exe"
    
    if not os.path.exists(soffice_path):
        raise FileNotFoundError(f"LibreOffice not found at: {soffice_path}. Please install LibreOffice or verify the path.")
        
    cmd = [
        soffice_path,
        "--headless",
        "--convert-to", "pdf",
        "--outdir", output_dir,
        docx_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            raise Exception(f"LibreOffice conversion failed.\nStdout: {result.stdout}\nStderr: {result.stderr}")
            
        # Determine the expected output path
        filename = os.path.basename(docx_path)
        pdf_filename = os.path.splitext(filename)[0] + ".pdf"
        expected_pdf_path = os.path.join(output_dir, pdf_filename)
        
        if not os.path.exists(expected_pdf_path):
             raise Exception(f"Conversion command succeeded but output PDF not found at {expected_pdf_path}")
             
        return expected_pdf_path
        
    except subprocess.TimeoutExpired:
        raise Exception("LibreOffice conversion timed out after 60 seconds.")
