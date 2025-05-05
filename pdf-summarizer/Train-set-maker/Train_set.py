# --- START OF FILE ui-train.py (Corrected v3) ---

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import time
from datetime import datetime
import re
import sys
import traceback # For logging exceptions

# --- Third-party imports ---
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_SUPPORT = True
except ImportError:
    DND_SUPPORT = False

try:
    import fitz  # PyMuPDF
except ImportError:
    messagebox.showerror("Error", "PyMuPDF not found. Please install it: pip install pymupdf")
    sys.exit(1)

try:
    import google.generativeai as genai
    from google.generativeai import types
except ImportError:
    messagebox.showerror("Error", "Google Generative AI library not found. Please install it: pip install google-generativeai")
    sys.exit(1)

try:
    from langdetect import detect, LangDetectException
except ImportError:
     messagebox.showerror("Error", "Langdetect library not found. Please install it: pip install langdetect")
     sys.exit(1)
# --- End Third-party imports ---


class PDFProcessorApp:
    # --- Constants for Text Cleaning ---
    MIN_CHARS_BETWEEN_MULTI_SPACE = 5
    MIN_LARGE_GAPS_TO_FILTER = 2
    multi_space_pattern = re.compile(r"\s{3,}")
    HEADERS_FOOTERS_TO_REMOVE = {
        "Press Information Bureau", "Government of India", "****",
        # Add other common headers/footers
    }
    url_pattern = re.compile(r'https?://\S+|www\.\S+')
    ref_pattern = re.compile(r'\[\d+\]')
    multi_newline_pattern = re.compile(r'\n{3,}')
    datetime_pattern = re.compile(r'^\d{1,2}-[A-Za-z]+-\d{4}\s+\d{1,2}:\d{1,2}\s+[A-Z]+$')
    # --- End Constants ---

    def __init__(self, root):
        self.root = root
        self.root.title("PDF Data Generator (v3 - Logging Fixed)")
        self.root.geometry("850x700") # Slightly taller for log

        self.log_file_handle = None # Initialize as None
        self.log_file_path = None   # Initialize log path too

        self.reset_stats_and_log() # Combined reset

        self.model = None
        if not self.configure_gemini():
            self.root.after(100, self.root.destroy)
            return

        self.create_widgets()
        self.pdf_files = []
        self.processing_active = False

    def reset_stats_and_log(self):
        """Resets processing statistics and closes any open log file handle."""
        self.processing_stats = {
            'total_files_in_list': 0,
            'processed_count': 0,
            'files_attempted': [],
            'per_file_details': [],
            'start_time': None,
            'end_time': None,
        }
        if self.log_file_handle and not self.log_file_handle.closed:
            try:
                self.log_file_handle.close()
                print("Previous log file handle closed.")
            except Exception as e:
                 print(f"Warning: Could not close previous log file handle: {e}")
        # Reset handle and path for the new session
        self.log_file_handle = None
        self.log_file_path = None # Explicitly reset path here too

    def configure_gemini(self):
        """Configure the Gemini API client. Returns True on success, False on failure."""
        try:
            API_KEY = os.getenv("GEMINI_API_KEY")
            if not API_KEY:
                messagebox.showerror("Config Error", "GEMINI_API_KEY environment variable not set.")
                return False

            genai.configure(api_key=API_KEY)
            self.model = genai.GenerativeModel(
                model_name="gemini-1.5-flash-latest",
                generation_config={"temperature": 0.6, "max_output_tokens": 2048},
                safety_settings=[
                    {"category": f"HARM_CATEGORY_{cat}", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
                    for cat in ["HARASSMENT", "HATE_SPEECH", "SEXUALLY_EXPLICIT", "DANGEROUS_CONTENT"]
                ]
            )
            print("Gemini API configured successfully.")
            return True
        except Exception as e:
             messagebox.showerror("Config Error", f"Failed to configure Gemini API: {e}")
             return False

    def create_widgets(self):
        """Create all UI elements"""
        # (Widget creation code remains the same)
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        drop_frame = ttk.LabelFrame(top_frame, text="Drag & Drop PDF Files Here", padding="10")
        drop_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        self.drop_label = ttk.Label(drop_frame, text="Drop PDF files here or click 'Add Files'", wraplength=400, anchor="center")
        self.drop_label.pack(fill=tk.BOTH, expand=True, ipady=20)
        if DND_SUPPORT:
            self.drop_label.drop_target_register(DND_FILES)
            self.drop_label.dnd_bind('<<Drop>>', self.on_drop)
        else:
             self.drop_label.config(text="Drop files here (requires tkinterdnd2) or click 'Add Files'")
        button_frame = ttk.Frame(top_frame)
        button_frame.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Button(button_frame, text="Add Files", command=self.add_files).pack(pady=2, fill=tk.X)
        ttk.Button(button_frame, text="Clear List", command=self.clear_files).pack(pady=2, fill=tk.X)
        ttk.Button(button_frame, text="Generate Dataset", command=self.process_files).pack(pady=(10, 2), fill=tk.X)
        file_list_frame = ttk.LabelFrame(main_frame, text="Files to Process", padding="5")
        file_list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        self.file_listbox = tk.Listbox(file_list_frame, selectmode=tk.EXTENDED, width=80)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(file_list_frame, command=self.file_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.config(yscrollcommand=scrollbar.set)
        progress_status_frame = ttk.Frame(main_frame)
        progress_status_frame.pack(fill=tk.X, pady=5)
        self.progress = ttk.Progressbar(progress_status_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(progress_status_frame, textvariable=self.status_var, anchor="e").pack(side=tk.RIGHT)
        console_frame = ttk.LabelFrame(main_frame, text="Processing Log (UI)", padding="5")
        console_frame.pack(fill=tk.BOTH, expand=True)
        self.console_text = tk.Text(console_frame, wrap=tk.WORD, height=12)
        self.console_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        console_scroll = ttk.Scrollbar(console_frame, command=self.console_text.yview)
        console_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.console_text.config(yscrollcommand=console_scroll.set)
        console_scroll.config(command=self.console_text.yview)


    def log_message(self, message, level="INFO", also_log_to_file=True):
        """Add message to UI console and optionally to the log file."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        ui_message = f"[{timestamp}][{level}] {message}\n"
        try:
             if self.root.winfo_exists(): self.root.after(0, lambda: self._update_ui_log(ui_message))
        except Exception as ui_update_error: print(f"Error scheduling UI update: {ui_update_error}")

        # Check log handle specifically before writing
        if also_log_to_file and hasattr(self, 'log_file_handle') and self.log_file_handle and not self.log_file_handle.closed:
            try:
                file_message = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [{level}] {message}\n"
                self.log_file_handle.write(file_message)
                self.log_file_handle.flush()
            except Exception as e:
                error_msg = f"[[Failed to write to log file: {e}]]"
                try:
                    if self.root.winfo_exists(): self.root.after(0, lambda: self._update_ui_log(error_msg + "\n"))
                except Exception as ui_update_error_inner: print(f"Error scheduling UI update for log write failure: {ui_update_error_inner}")
        elif also_log_to_file:
            # Log handle doesn't exist or is closed, print warning to console if trying to log
             print(f"Warning: Log file handle not available or closed when trying to log: {message}")


    def _update_ui_log(self, message):
        """Helper method to update the UI log safely."""
        # (Same logic as before)
        try:
            if self.console_text.winfo_exists():
                self.console_text.insert(tk.END, message)
                self.console_text.see(tk.END)
            else: print("UI Log widget destroyed, cannot update.")
        except tk.TclError as e: print(f"Error updating UI log (window likely closed or widget destroyed): {e}")
        except Exception as e: print(f"Unexpected error updating UI log: {e}")


    # --- UI Interaction Methods ---
    # (on_drop, add_files, add_pdf_files, clear_files, update_file_list remain the same)
    def on_drop(self, event):
        try:
            files = self.root.tk.splitlist(event.data)
            pdf_files_dropped = [f for f in files if f.lower().endswith('.pdf')]
            if not pdf_files_dropped: messagebox.showwarning("No PDFs", "No PDF files found in the dropped items."); return
            self.add_pdf_files(pdf_files_dropped)
        except Exception as e: messagebox.showerror("Drop Error", f"Failed to handle dropped files: {e}")

    def add_files(self):
        files = filedialog.askopenfilenames(title="Select PDF Files", filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")])
        if files: self.add_pdf_files(files)

    def add_pdf_files(self, files_to_add):
        new_files_count = 0
        for f in files_to_add:
            norm_f = os.path.normpath(f)
            if norm_f not in self.pdf_files:
                self.pdf_files.append(norm_f)
                new_files_count += 1
        if new_files_count == 0: messagebox.showinfo("Info", "Selected PDF file(s) are already in the list."); return
        self.update_file_list()
        self.log_message(f"Added {new_files_count} PDF(s). Total: {len(self.pdf_files)}", also_log_to_file=False)

    def clear_files(self):
        if self.processing_active: messagebox.showwarning("Busy", "Cannot clear list while processing is active."); return
        self.pdf_files = []
        self.update_file_list()
        self.log_message("File list cleared", also_log_to_file=False)

    def update_file_list(self):
        try:
             if self.file_listbox.winfo_exists():
                self.file_listbox.delete(0, tk.END)
                for file in self.pdf_files:
                    self.file_listbox.insert(tk.END, os.path.basename(file))
        except tk.TclError: print("File listbox destroyed, cannot update.")
        except Exception as e: print(f"Error updating file listbox: {e}")
    # --- End UI Interaction Methods ---


    # --- Text Extraction and Cleaning Logic ---
    # (extract_and_clean_text and helpers remain the same)
    def is_likely_table_line(self, line):
        line = line.strip(); gaps = list(self.multi_space_pattern.finditer(line))
        if len(gaps) >= self.MIN_LARGE_GAPS_TO_FILTER:
            last_pos=0; short_segment_count=0
            for gap in gaps:
                start,_=gap.span(); segment=line[last_pos:start].strip()
                if 0<len(segment)<self.MIN_CHARS_BETWEEN_MULTI_SPACE: short_segment_count+=1
                last_pos=gap.span()[1]
            segment=line[last_pos:].strip()
            if 0<len(segment)<self.MIN_CHARS_BETWEEN_MULTI_SPACE: short_segment_count+=1
            if short_segment_count>0: return True
        return False

    def extract_and_clean_text(self, pdf_path):
        doc = None; filename = os.path.basename(pdf_path); t_start = time.time()
        try:
            doc = fitz.open(pdf_path)
            full_text_unfiltered = "".join([page.get_text("text", sort=True) + "\n" for page in doc])
            cleaned_lines=[]; lines_filtered_table, lines_filtered_header, lines_filtered_datetime = 0,0,0
            for line in full_text_unfiltered.splitlines():
                cleaned_line = line.strip()
                if not cleaned_line: continue
                if self.datetime_pattern.fullmatch(cleaned_line): lines_filtered_datetime += 1; continue
                if cleaned_line in self.HEADERS_FOOTERS_TO_REMOVE: lines_filtered_header += 1; continue
                # if self.is_likely_table_line(cleaned_line): lines_filtered_table += 1; continue
                cleaned_line = self.url_pattern.sub('', cleaned_line)
                cleaned_line = self.ref_pattern.sub('', cleaned_line).strip()
                if cleaned_line: cleaned_lines.append(cleaned_line)
            final_text = "\n".join(cleaned_lines)
            final_text = self.multi_newline_pattern.sub('\n\n', final_text).strip()
            final_text = re.sub(r' +', ' ', final_text)
            t_end = time.time(); duration = t_end - t_start
            self.log_message(f"Text extraction/cleaning for {filename} took {duration:.2f}s", level="DEBUG")
            return final_text, duration
        except Exception as e:
            t_end = time.time(); duration = t_end - t_start
            self.log_message(f"Error extracting/cleaning text from {filename}: {e}", level="ERROR")
            return None, duration
        finally:
            if doc: doc.close()
    # --- End Text Extraction Logic ---

    # --- Gemini API Call Logic ---
    # (generate_summary_and_topics and helpers remain the same)
    def generate_summary_and_topics(self, pdf_text, pdf_filename):
        if not self.model: self.log_message("Gemini model not configured.", level="ERROR"); return None, None, 0.0
        if not pdf_text or len(pdf_text) < 50: self.log_message(f"Skipping Gemini for '{pdf_filename}' due to insufficient text.", level="WARN"); return None, None, 0.0
        t_start = time.time()
        try:
            prompt = f"""
            Analyze the following text extracted from a government PDF document ('{pdf_filename}')...
            --- SUMMARY START ---
            [Your generated summary here...]
            --- SUMMARY END ---
            --- TOPICS JSON START ---
            [ {{"main_topic": "Topic 1"}}, {{"main_topic": "Topic 2"}} ... ]
            --- TOPICS JSON END ---
            --- BEGIN PDF TEXT ---
            {pdf_text[:40000]}
            --- END PDF TEXT ---
            """
            self.log_message(f"Sending text from '{pdf_filename}' to Gemini...", level="DEBUG")
            response = self.model.generate_content(prompt)
            t_end = time.time(); duration = t_end - t_start
            if not response.parts: raise ValueError(f"Received empty response or blocked content. Safety feedback: {response.prompt_feedback if hasattr(response, 'prompt_feedback') else 'N/A'}")
            if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
                 finish_reason = response.candidates[0].finish_reason if response.candidates else 'N/A'
                 raise ValueError(f"Received response with no content parts. Finish reason: {finish_reason}")
            response_text = response.text
            summary = self.extract_between_markers(response_text, "--- SUMMARY START ---", "--- SUMMARY END ---")
            topics_json_str = self.extract_between_markers(response_text, "--- TOPICS JSON START ---", "--- TOPICS JSON END ---")
            if summary is None or topics_json_str is None: raise ValueError("Could not parse Gemini response markers.")
            topics = None
            try:
                json_string_cleaned = "\n".join(line for line in topics_json_str.splitlines() if not line.strip().startswith('//'))
                topics = json.loads(json_string_cleaned)
                if not isinstance(topics, list): raise TypeError(f"Parsed topics is not a list, got {type(topics)}.")
            except (json.JSONDecodeError, TypeError) as json_e:
                self.log_message(f"Invalid topics JSON format for {pdf_filename}: {json_e}", level="WARN")
                self.log_message(f"RAW JSON STRING for {pdf_filename}:\n{topics_json_str}", level="DEBUG")
                return summary, None, duration
            self.log_message(f"Gemini API call for {pdf_filename} took {duration:.2f}s", level="DEBUG")
            return summary, topics, duration
        except (types.StopCandidateException, types.BlockedPromptException, ValueError, Exception) as e:
            t_end = time.time(); duration = t_end - t_start
            self.log_message(f"Gemini API error processing {pdf_filename} ({type(e).__name__}): {e}", level="ERROR")
            return None, None, duration
    # --- End Gemini API Call Logic ---

    def extract_between_markers(self, text, start_marker, end_marker):
        start_idx = text.find(start_marker);
        if start_idx == -1: return None
        start_idx += len(start_marker)
        end_idx = text.find(end_marker, start_idx)
        if end_idx == -1: return None
        return text[start_idx:end_idx].strip()

    # --- Main Processing Logic ---
    def process_files(self):
        """Process all PDF files, save to JSONL, and generate detailed log file."""
        if self.processing_active: messagebox.showwarning("Busy", "Processing already in progress."); return
        if not self.pdf_files: messagebox.showwarning("No Files", "No PDF files added."); return

        output_jsonl_path = filedialog.asksaveasfilename(
            title="Save Dataset As", defaultextension=".jsonl",
            filetypes=[("JSON Lines", "*.jsonl"), ("All Files", "*.*")]
        )
        if not output_jsonl_path:
            self.log_message("Output file selection cancelled.", level="INFO", also_log_to_file=False)
            return # Exit if user cancelled

        # --- FIX: Rearrange the setup sequence ---
        self.processing_active = True # Set flag now
        self.reset_stats_and_log() # Reset stats AND log file handle/path
        self.processing_stats['total_files_in_list'] = len(self.pdf_files)
        self.processing_stats['start_time'] = time.time()

        # Derive log file path AFTER reset
        try:
            base_path, _ = os.path.splitext(output_jsonl_path)
            self.log_file_path = base_path + "_log.txt" # Assign the path attribute
        except Exception as path_e:
             messagebox.showerror("Path Error", f"Could not derive log file path from '{output_jsonl_path}': {path_e}")
             self.processing_active = False
             return

        # Open log file immediately AFTER deriving the path and resetting
        try:
            log_dir = os.path.dirname(self.log_file_path)
            if log_dir and not os.path.exists(log_dir):
                 os.makedirs(log_dir); print(f"Created directory for log file: {log_dir}")

            self.log_file_handle = open(self.log_file_path, 'w', encoding='utf-8') # Now self.log_file_path is set
            self.log_message(f"Starting processing session.", level="SESSION", also_log_to_file=True)
            self.log_message(f"Dataset file: {output_jsonl_path}", level="SESSION", also_log_to_file=True)
            self.log_message(f"Log file: {self.log_file_path}", level="SESSION", also_log_to_file=True)
            self.log_message(f"Processing {len(self.pdf_files)} files...", level="SESSION", also_log_to_file=True)
        except Exception as e:
             messagebox.showerror("Log File Error", f"Failed to open log file '{self.log_file_path}': {e}")
             self.processing_active = False
             # Clean up: Make sure handle is None if open failed
             if self.log_file_handle and not self.log_file_handle.closed: self.log_file_handle.close()
             self.log_file_handle = None
             self.log_file_path = None # Also reset path if opening failed
             return
        # --- END FIX ---

        self.progress["maximum"] = len(self.pdf_files)
        self.progress["value"] = 0
        self.root.update() # Update UI to show progress bar max

        jsonl_outfile = None
        try:
            jsonl_outfile = open(output_jsonl_path, 'w', encoding='utf-8')
            for i, pdf_path in enumerate(self.pdf_files):
                # --- Start of loop ---
                self.processing_stats['processed_count'] += 1
                filename = os.path.basename(pdf_path)
                self.processing_stats['files_attempted'].append(filename)
                self.status_var.set(f"Processing {i+1}/{len(self.pdf_files)}: {filename}")
                self.log_message(f"--- Starting: {filename} ({i+1}/{len(self.pdf_files)}) ---", level="INFO")

                file_details = {'filename': filename, 'status': 'UNKNOWN', 'reason': '', 'extraction_time': 0.0, 'gemini_time': 0.0}

                # 1. Extract Text
                extracted_text, extract_duration = self.extract_and_clean_text(pdf_path)
                file_details['extraction_time'] = round(extract_duration, 2)
                if extracted_text is None:
                    file_details.update({'status': 'FAIL', 'reason': 'Text extraction/cleaning failed'})
                    self.processing_stats['per_file_details'].append(file_details)
                    self.progress["value"] = i + 1; self.root.update_idletasks(); continue

                # 2. Language Detection
                lang = 'en'; 
                try:
                    sample_text = extracted_text[:1500]
                    if len(sample_text.strip()) < 20: lang = 'unknown'
                    else: lang = detect(sample_text)
                    if lang != 'en' and lang != 'unknown':
                        file_details.update({'status': 'SKIP', 'reason': f'Detected language: {lang}'})
                        self.processing_stats['per_file_details'].append(file_details); self.log_message(f"Skipping {filename} (Lang: {lang})", level="WARN")
                        self.progress["value"] = i + 1; self.root.update_idletasks(); continue
                    elif lang == 'unknown': self.log_message(f"Lang detection inconclusive for {filename}. Proceeding.", level="WARN")
                    else: self.log_message(f"Lang detected as English for {filename}.", level="DEBUG")
                except (LangDetectException, Exception) as lang_e: self.log_message(f"Lang detection failed/error for {filename}: {lang_e}. Proceeding.", level="WARN")

                # 3. Gemini API Call
                summary, topics, gemini_duration = self.generate_summary_and_topics(extracted_text, filename)
                file_details['gemini_time'] = round(gemini_duration, 2)

                # 4. Prepare and Write Record
                data_record = {"pdf_filename": filename, "extracted_text": extracted_text,"gemini_summary": summary,"gemini_topics": topics}
                try:
                    json.dump(data_record, jsonl_outfile); jsonl_outfile.write('\n'); jsonl_outfile.flush()
                    if summary is not None:
                        reason_detail = 'Summary generated' + (' (Topics parsing failed)' if topics is None else '')
                        file_details.update({'status': 'SUCCESS', 'reason': reason_detail}); self.log_message(f"Wrote record for {filename}", level="INFO")
                    else: file_details.update({'status': 'FAIL', 'reason': 'Gemini generation failed'})
                except Exception as write_e:
                     self.log_message(f"Failed to write JSON record for {filename}: {write_e}", level="ERROR")
                     file_details.update({'status': 'FAIL', 'reason': f'JSON writing error: {write_e}'})
                self.processing_stats['per_file_details'].append(file_details)

                # 5. Rate Limiting
                # self.log_message(f"Waiting 3s rate limit...", level="DEBUG")
                time.sleep(0.05)

                self.progress["value"] = i + 1
                self.root.update_idletasks()
                self.log_message(f"--- Finished: {filename} ---", level="INFO")
                # --- End of loop ---

        except Exception as e:
            self.log_message(f"CRITICAL ERROR during processing loop: {e}", level="CRITICAL")
            self.log_message(traceback.format_exc(), level="CRITICAL")
            messagebox.showerror("Processing Error", f"A critical error occurred: {e}\nProcessing stopped. Check log file.")
            file_details = {'filename': 'Processing Loop', 'status': 'FAIL', 'reason': f'Critical Error: {e}', 'extraction_time': 0.0, 'gemini_time': 0.0}
            self.processing_stats['per_file_details'].append(file_details)
        finally:
            # Ensure JSONL file is closed if opened
            if jsonl_outfile and not jsonl_outfile.closed:
                try: jsonl_outfile.close(); self.log_message("Closed dataset file.", level="DEBUG", also_log_to_file=True)
                except Exception as e: self.log_message(f"Error closing dataset file: {e}", level="ERROR")

            # Final wrap-up: reset flag, finalize stats, close log, show message
            self.processing_active = False
            self.processing_stats['end_time'] = time.time()
            self.write_final_log_summary() # Write summary to log file
            if self.log_file_handle and not self.log_file_handle.closed:
                self.log_file_handle.close()
                self.log_file_handle = None # Set handle to None

            # Calculate final counts
            success_count = sum(1 for d in self.processing_stats['per_file_details'] if d['status'] == 'SUCCESS')
            skipped_count = sum(1 for d in self.processing_stats['per_file_details'] if d['status'] == 'SKIP')
            failed_count = sum(1 for d in self.processing_stats['per_file_details'] if d['status'] == 'FAIL')
            processed_count = self.processing_stats['processed_count']
            total_listed = self.processing_stats['total_files_in_list']

            final_status_msg = f"Completed! {success_count}/{processed_count} generated. {skipped_count} skipped. {failed_count} failed."
            self.status_var.set(final_status_msg)
            log_path_to_show = self.log_file_path if self.log_file_path else "N/A (Log file not created)"
            jsonl_path_to_show = output_jsonl_path if output_jsonl_path else 'N/A (Cancelled)'

            # Use root.after for final UI updates to prevent potential blocking/errors
            self.root.after(0, lambda: self.log_message(f"\n--- Processing Complete ---", level="SESSION", also_log_to_file=False))
            self.root.after(10, lambda: self.log_message(final_status_msg, level="SESSION", also_log_to_file=False))

            self.root.after(100, lambda: messagebox.showinfo(
                "Complete",
                f"Processing finished.\n\n"
                f"Total files in list: {total_listed}\n"
                f"Files attempted: {processed_count}\n"
                f"Successfully generated: {success_count}\n"
                f"Skipped (non-English): {skipped_count}\n"
                f"Failed: {failed_count}\n\n"
                f"Dataset saved to: {jsonl_path_to_show}\n"
                f"Detailed log saved to: {log_path_to_show}"
            ))
            self.log_file_path = None # Reset log path after processing done


    def write_final_log_summary(self):
        """Writes the summary and detailed per-file results to the log file."""
        # Check added here for safety, although the finally block logic should handle it
        if not self.log_file_handle or self.log_file_handle.closed:
             print("Log file handle not available or closed, cannot write final summary to file.")
             return

        try:
            # (Same summary writing logic as before)
            self.log_file_handle.write("\n\n--- Processing Summary ---\n")
            start_time=self.processing_stats['start_time']; end_time=self.processing_stats['end_time'] if self.processing_stats['end_time'] else time.time(); total_duration=end_time - start_time if start_time else 0
            total_listed=self.processing_stats['total_files_in_list']; processed_count=self.processing_stats['processed_count']
            success_count=sum(1 for d in self.processing_stats['per_file_details'] if d['status']=='SUCCESS'); skipped_count=sum(1 for d in self.processing_stats['per_file_details'] if d['status']=='SKIP'); failed_count=sum(1 for d in self.processing_stats['per_file_details'] if d['status']=='FAIL')
            self.log_file_handle.write(f"Start Time: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S') if start_time else 'N/A'}\n")
            self.log_file_handle.write(f"End Time: {datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.log_file_handle.write(f"Total Duration: {total_duration:.2f} seconds\n\n")
            self.log_file_handle.write(f"Total Files in List: {total_listed}\n"); self.log_file_handle.write(f"Files Attempted Processing: {processed_count}\n")
            self.log_file_handle.write(f"Successfully Generated & Written: {success_count}\n"); self.log_file_handle.write(f"Skipped (Non-English/Other): {skipped_count}\n"); self.log_file_handle.write(f"Failed: {failed_count}\n")
            self.log_file_handle.write("\n--- Detailed File Log ---\n"); header = f"{'Filename':<45} | {'Status':<8} | {'Extract(s)':<11} | {'Gemini(s)':<10} | Reason / Details\n"; self.log_file_handle.write(header); self.log_file_handle.write("-" * (len(header)+5) + "\n")
            for details in self.processing_stats['per_file_details']:
                 filename=details.get('filename','N/A'); status=details.get('status','N/A'); reason=details.get('reason',''); ext_t=f"{details.get('extraction_time',0.0):.2f}"
                 gem_t=f"{details.get('gemini_time',0.0):.2f}" if status=='SUCCESS' or (status=='FAIL' and details.get('gemini_time',0.0) > 0) else "-"
                 display_filename=(filename[:42]+'...') if len(filename)>45 else filename; log_line=f"{display_filename:<45} | {status:<8} | {ext_t:<11} | {gem_t:<10} | {reason}\n"; self.log_file_handle.write(log_line)
            self.log_file_handle.write("-" * (len(header)+5) + "\n"); self.log_file_handle.write("--- End of Log ---\n"); self.log_file_handle.flush()
        except Exception as e:
            print(f"Error writing final log summary: {e}")
            try:
                 if self.root.winfo_exists(): self.root.after(0, lambda: self.log_message(f"Error writing final summary to log file: {e}", level="ERROR", also_log_to_file=False))
            except Exception: pass


# --- Main Execution Block ---
if __name__ == "__main__":
    if DND_SUPPORT: root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
        root.after(100, lambda: messagebox.showwarning( "Warning", "Drag-and-drop support is not available.\nInstall 'tkinterdnd2': pip install tkinterdnd2"))

    app = PDFProcessorApp(root)
    root.mainloop()

# --- END OF FILE ui-train.py (Corrected v3) ---