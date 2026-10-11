#!/usr/bin/env python3
"""
Window: ingredients in fridge, recipe from Gemini.
Enhanced with Dietary Filters, PDF Export, and CO2 Savings Tracker (No Images).
"""

import os
import sys
import threading
import io
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext, ttk, filedialog, messagebox

# --- BLOCCO DI AUTO-INSTALLAZIONE AUTOMATICA INTERNA (Solo ReportLab e SDK) ---
import subprocess
try:
    from google import genai
    from google.genai import types
except ModuleNotFoundError:
    print("Librerie mancanti. Installazione automatica dei requisiti...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "google-genai", "reportlab"])
    from google import genai
    from google.genai import types
# -----------------------------------------------------------------------------

MODELS = ("gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-3.5-flash")
KEY_PATH = Path(__file__).with_name(".key")

PROMPT = """You only have these ingredients in your fridge:
{ingredients}

Dietary Preference/Restriction: {diet}

Propose a realistic recipe in English, including:
- dish name (Clearly state it on the first line as "Dish Name: [Name]")
- quantities/dosages
- numbered steps
- estimated time

You can assume salt, pepper, oil, and water are available. If an essential ingredient is missing, mention it and still propose the closest version with what is available.

At the very end of your response, add a section called "--- ECO IMPACT ---" and estimate the approximate CO2 savings (in kg) achieved by choosing to cook these ingredients instead of letting them go to waste and driving to buy fast food. Explain the reasoning very briefly in one sentence."""

def saved_key():
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value: return value
    if KEY_PATH.exists(): return KEY_PATH.read_text(encoding="utf-8").strip()
    return ""

def save_key(key):
    KEY_PATH.write_text(key.strip() + "\n", encoding="utf-8")
    KEY_PATH.chmod(0o600)

def model_should_be_replaced(error):
    code = getattr(error, "code", None)
    if code in (404, 408, 429, 500, 502, 503, 504): return True
    text = str(error).upper()
    return any(sign in text for sign in ("UNAVAILABLE", "HIGH DEMAND", "NOT FOUND", "RESOURCE_EXHAUSTED"))
def ask_for_recipe(ingredients, diet, key, notify=None):
    ingredients, key = ingredients.strip(), key.strip()
    if not ingredients: raise ValueError("Please write at least one ingredient.")
    if not key: raise RuntimeError("Paste your free Google AI Studio key in the field above.")
    client = genai.Client(api_key=key, http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)))
    recipe_text = ""
    last_error = None
    for model in MODELS:
        if notify: notify(f"Asking {model} for recipe...")
        try:
            response = client.models.generate_content(model=model, contents=PROMPT.format(ingredients=ingredients, diet=diet))
        except Exception as exc:
            last_error = exc
            if model_should_be_replaced(exc): continue
            raise
        text = (response.text or "").strip()
        if text:
            recipe_text = text
            break
    if not recipe_text: raise RuntimeError("Gemini is overloaded.\n\n" + str(last_error or ""))
    return recipe_text

def main_gui(initial_ingredients):
    root = tk.Tk()
    root.title("SmartFridge AI - What's Cooking?")
    root.geometry("700x650")
    root.configure(bg="#f4f1ea")
    container = ttk.Frame(root, padding=16)
    container.pack(fill="both", expand=True)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(4, weight=1)
    
    ttk.Label(container, text="SmartFridge AI 🍳", font=("DejaVu Sans", 18, "bold")).grid(row=0, column=0, sticky="w")
    
    key_var = tk.StringVar(value=saved_key())
    key_row = ttk.Frame(container)
    key_row.grid(row=2, column=0, sticky="ew", pady=8)
    ttk.Label(key_row, text="Gemini Key:").pack(side="left")
    ttk.Entry(key_row, textvariable=key_var, show="*", width=50).pack(side="left", fill="x", expand=True)
    
    filter_row = ttk.Frame(container)
    filter_row.grid(row=3, column=0, sticky="ew", pady=4)
    ttk.Label(filter_row, text="Dietary Filter:").pack(side="left")
    diet_var = tk.StringVar(value="None")
    diet_box = ttk.Combobox(filter_row, textvariable=diet_var, state="readonly")
    diet_box['values'] = ("None", "Vegetarian", "Vegan", "Gluten-Free", "Keto")
    diet_box.pack(side="left")
    
    left_frame = ttk.Frame(container)
    left_frame.grid(row=4, column=0, sticky="nsew", pady=4)
    left_frame.columnconfigure(0, weight=1)
    left_frame.rowconfigure(1, weight=1)
    
    text_input = scrolledtext.ScrolledText(left_frame, height=4, wrap="word")
    text_input.grid(row=0, column=0, sticky="ew", pady=4)
    text_input.insert("1.0", "2 eggs, 1 tomato, half onion")
    
    text_output = scrolledtext.ScrolledText(left_frame, height=15, wrap="word", state="disabled")
    text_output.grid(row=1, column=0, sticky="nsew")
    
    bar = ttk.Frame(container, padding=4)
    bar.grid(row=5, column=0, sticky="ew", pady=8)
    status = tk.StringVar(value="Ready.")
    current_data = {"text": ""}
    
    def write(t):
        text_output.configure(state="normal")
        text_output.delete("1.0", "end")
        text_output.insert("1.0", t)
        text_output.configure(state="disabled")
        
    def export_pdf():
        if not current_data["text"]: return
        fp = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not fp: return
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            doc = SimpleDocTemplate(fp, pagesize=letter)
            story = [Paragraph("SmartFridge AI Recipe", getSampleStyleSheet()['Heading1']), Spacer(1,12)]
            for line in current_data["text"].split('\n'):
                if line.strip(): story.append(Paragraph(line, getSampleStyleSheet()['Normal']))
            doc.build(story)
            messagebox.showinfo("Success", "PDF Saved!")
        except:
            Path(fp).with_suffix(".txt").write_text(current_data["text"], encoding="utf-8")
            
    def search():
        button.configure(state="disabled")
        status.set("Loading...")
        def worker():
            try:
                r = ask_for_recipe(text_input.get("1.0", "end"), diet_var.get(), key_var.get(), lambda m: root.after(0, lambda: status.set(m)))
                current_data["text"] = r
                root.after(0, lambda: (write(r), status.set("Done."), button.configure(state="normal"), pdf_button.configure(state="normal")))
            except Exception as e:
                root.after(0, lambda: (write(str(e)), status.set("Error."), button.configure(state="normal")))
        threading.Thread(target=worker, daemon=True).start()
        
    button = ttk.Button(bar, text="Find Recipe", command=search)
    button.pack(side="left")
    pdf_button = ttk.Button(bar, text="Export PDF", command=export_pdf, state="disabled")
    pdf_button.pack(side="left", padx=4)
    ttk.Label(bar, textvariable=status).pack(side="left", padx=8)
    root.mainloop()

if __name__ == "__main__":
    main_gui("")
