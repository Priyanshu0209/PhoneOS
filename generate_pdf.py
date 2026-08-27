import os
import markdown
from xhtml2pdf import pisa

def convert_md_to_pdf(md_path, pdf_path):
    with open(md_path, 'r', encoding='utf-8') as f:
        md_text = f.read()

    # Convert markdown to html
    html_content = markdown.markdown(md_text, extensions=['fenced_code', 'tables'])

    # Add some CSS to make it look professional
    full_html = f"""
    <html>
    <head>
    <style>
        @page {{
            size: a4 portrait;
            margin: 2cm;
            @frame header_frame {{
                -pdf-frame-content: header_content;
                left: 50pt; width: 512pt; top: 30pt; height: 30pt;
            }}
            @frame footer_frame {{
                -pdf-frame-content: footer_content;
                left: 50pt; width: 512pt; top: 772pt; height: 20pt;
            }}
        }}
        body {{
            font-family: Helvetica, Arial, sans-serif;
            font-size: 11pt;
            color: #333333;
            line-height: 1.5;
        }}
        h1 {{
            color: #2c3e50;
            font-size: 24pt;
            border-bottom: 2px solid #2c3e50;
            padding-bottom: 5px;
            margin-top: 20px;
        }}
        h2 {{
            color: #2980b9;
            font-size: 18pt;
            border-bottom: 1px solid #bdc3c7;
            padding-bottom: 3px;
            margin-top: 15px;
        }}
        h3 {{
            color: #34495e;
            font-size: 14pt;
            margin-top: 10px;
        }}
        code {{
            font-family: Courier, monospace;
            background-color: #f8f9fa;
            padding: 2px 4px;
            border: 1px solid #e9ecef;
            border-radius: 4px;
        }}
        pre {{
            background-color: #f8f9fa;
            padding: 10px;
            border: 1px solid #e9ecef;
            border-radius: 4px;
            font-family: Courier, monospace;
            font-size: 10pt;
            white-space: pre-wrap;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        th, td {{
            border: 1px solid #bdc3c7;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background-color: #ecf0f1;
            color: #2c3e50;
        }}
        hr {{
            border: 0;
            border-top: 1px solid #bdc3c7;
            margin: 20px 0;
        }}
        ul, ol {{
            margin-bottom: 10px;
        }}
    </style>
    </head>
    <body>
        <div id="header_content">PhoneOS — Setup & Deployment Manual</div>
        <div id="footer_content">Page <pdf:pagenumber> of <pdf:pagecount></div>
        {html_content}
    </body>
    </html>
    """

    with open(pdf_path, "w+b") as out_pdf:
        pisa_status = pisa.CreatePDF(
            src=full_html,
            dest=out_pdf
        )

    return pisa_status.err

md_file = os.path.expanduser("~/Documents/PhoneOS_Manual.md")
pdf_file = os.path.expanduser("~/Documents/PhoneOS_Complete_Replication_Setup_and_Deployment_Manual.pdf")

error = convert_md_to_pdf(md_file, pdf_file)
if error:
    print("PDF generation failed with errors.")
else:
    print("PDF generated successfully.")

