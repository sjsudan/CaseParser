# LegalParser ⚖️

> **Automated Court Causelist Matching Engine**
> *Reduce manual legal data entry time by 90% via PDF Parsing and Fuzzy Matching.*

`LegalParser` is a specialized Python automation tool designed for legal professionals. It solves the critical "Daily Causelist" problem: efficiently finding which of your firm's internal files are listed for hearing in the daily court PDF schedule.

Instead of manually CTRL+F searching hundreds of case numbers, this tool parses the PDF, normalizes the data, and matches it against your internal Master Database using a multi-step fuzzy matching algorithm.

## 🚀 Features

* **📄 PDF Intelligence:** Extracts structured case data (Case Number, Party Name, Sr. No.) from unstructured court PDFs using `pdfplumber` and Regex.
* **🧠 Fuzzy Matching Algorithm:** Matches cases even if there are typos in the Cause List (e.g., matching "WP(C) 1/23" to "WPC 01/2023").
* **🔗 Clubbed Case Detection:** Automatically detects and extracts "Connected/Clubbed" cases hidden inside the main case text blocks.
* **🧹 Data Normalization:** Standardizes years (2023 -> 23) and case types to ensure accurate cross-referencing.
* **📊 Excel Reporting:** Generates a clean Excel report highlighting exactly which physical files need to be retrieved for the next hearing.

## 🛠️ Tech Stack

* **Python 3.9+**
* **Pandas:** For high-performance data handling and Excel generation.
* **PDFPlumber:** For robust text extraction from PDF documents.
* **XlsxWriter:** For formatting the output Excel sheets automatically.
* **Regex (re):** For pattern recognition and data cleaning.

## ⚙️ Installation

1.  Clone the repository:
    ```bash
    git clone [https://github.com/sjsudan/legal-parser.git](https://github.com/sjsudan/legal-parser.git)
    cd legal-parser
    ```

2.  Install dependencies:
    ```bash
    pip install pandas pdfplumber xlsxwriter openpyxl
    ```

## 📖 Usage

Run the script from the command line by providing your Master Database (Excel/CSV) and the Court Causelist (PDF).

```bash
python legalparser.py --master master_data.xlsx --query daily_list.pdf --out results.xlsx
