# CV Parser

A robust, local Python tool to extract structured data from CVs (PDF, DOCX, TXT) using NLP and ML. No Colab or notebook dependencies.

## Features

- Extracts name, contact info, education, experience, skills, job titles, and more
- CLI interface: parse and save results as JSON
- Robust to missing CSVs (uses built-in fallback lists)
- Works on Windows and Linux

## Installation

   ```
1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Download required NLP models:
   ```
   python -m spacy download en_core_web_sm
   python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
   ```

## Usage

Run the parser from the command line:

```
python cv_parser.py --input "mycv.pdf" --output "out.json"
```

Optional: print the parsed JSON to the terminal:

```
python cv_parser.py --input "mycv.pdf" --output "out.json" --print
```

## Data Files (Optional)

- Place `skills.csv` and `job_titles.csv` in the root directory for custom skill/job title lists.
- If missing, built-in fallback lists are used.

## Output

- The output is a JSON file with all extracted fields.

## Troubleshooting

- If you see missing dependency errors, ensure you have run all install steps above.
- For spaCy and NLTK, make sure the models are downloaded as shown above.

## License

MIT
