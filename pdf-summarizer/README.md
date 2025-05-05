# PDF Summarizer using Seq2Seq with Attention

This project implements a complete pipeline to generate summaries from PDFs using a custom-trained Sequence-to-Sequence (Seq2Seq) model with attention in TensorFlow. It includes text extraction, preprocessing, training with a SentencePiece tokenizer, and summary generation using both greedy and beam search methods.

## 🔍 Features

- Extracts text from government-style PDFs
- Tokenization using SentencePiece subword tokenizer
- Encoder-Decoder architecture with Attention mechanism (LSTM-based)
- Custom training loop with scheduled sampling
- Summary generation using Greedy and Beam Search decoding
- ROUGE evaluation for summarization quality

# VakyaSaar: PDF Summarizer for Government Press Releases 🇮🇳

VakyaSaar is a full-stack pipeline for collecting, cleaning, and summarizing Indian government press release PDFs. It combines web scraping, PDF text extraction, and both **LLM-based** (Gemini 1.5 Flash) and **custom Seq2Seq with Attention** models for high-quality text summarization.

---

## 📌 Project Components

### 🔹 1. PIB Scraper

Scrapes press releases from the [PIB Southern Region](https://pib.gov.in/allRel.aspx?reg=20&lang=1):

- Asynchronously scrapes all press release metadata (title, date, link)
- Filters English-language PDFs only
- Downloads and extracts clean text from PDFs
- Stores output in `all_pdf_data.jsonl`

> 📁 Script: `Train_set.py`

---

### 🔹 2. LLM-Based Summarization (Gemini 1.5 Flash)

- Uses Google's **Gemini 1.5 Flash** via Vertex AI or AI Studio API
- Summarizes extracted text from PDFs
- Provides fast and fluent summaries for government documentation
- Ideal for production usage and quick evaluations

---

### 🔹 3. Seq2Seq Summarization Pipeline (Custom Model)

Implements a full NLP pipeline in TensorFlow:

- Tokenization using **SentencePiece** (subword units)
- Encoder-Decoder **LSTM model with Bahdanau Attention**
- Trained on extracted PIB text + human summaries
- Supports **greedy decoding** and **beam search**
- Evaluated using **ROUGE scores**

> 📓 Notebook: `pdf_summarizer_seq2seq.ipynb`  
> 📁 Tokenizer: `tokenizer/pib_summarizer_spm_50k.model`

---

## 📁 Directory Structure


## 🛠️ Setup

1. Clone this repository
2. (Optional) Create a virtual environment
3. Install dependencies:

```bash
pip install -r requirements.txt
```

## 📁 Repository Structure

```
pdf-summarizer/
├── pdf_summarizer_seq2seq.ipynb        # Main notebook
├── tokenizer/
│   ├── pib_summarizer_spm_50k.model     # SentencePiece model file
│   └── pib_summarizer_spm_50k.vocab     # SentencePiece vocab file
|
├── requirements.txt                    # Python dependencies
├── README.md                           # Project overview and usage
└── sample_pdfs/
    └── example.pdf                     # Example input
```

## 🧪 Usage

Run the notebook `pdf_summarizer_seq2seq.ipynb` to:

1. Load or train the tokenizer
2. Prepare the dataset
3. Train the Seq2Seq model
4. Generate summaries from extracted text or PDFs

## 🧠 Model

The architecture uses:
- Embedding layer
- LSTM encoder & decoder
- Attention mechanism (Bahdanau-style)
- Beam search decoding for better summary quality

## 📊 Evaluation

Evaluation is performed using ROUGE scores comparing generated summaries with ground-truth summaries.
