import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import datetime
import os
import json
from ecourts import search_by_cnr, search_by_case, get_cause_list_for_court, download_file, check_listing_in_causelist


class ECourtsGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("eCourts Scraper")
        self.root.geometry("800x600")
        self.root.resizable(False, False)

        self.tab_control = ttk.Notebook(root)
        self.tab_control.pack(expand=1, fill='both')

        self.search_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.search_tab, text='Search Case')

        self.causelist_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.causelist_tab, text='Cause List')

        self.build_search_tab()
        self.build_causelist_tab()

    def build_search_tab(self):
        frame = self.search_tab

        cnr_frame = ttk.LabelFrame(frame, text="Search by CNR")
        cnr_frame.pack(fill="x", padx=10, pady=5)
        self.cnr_entry = ttk.Entry(cnr_frame, width=30)
        self.cnr_entry.pack(side="left", padx=5, pady=5)
        ttk.Label(cnr_frame, text="CNR Number").pack(side="left", padx=5)

        case_frame = ttk.LabelFrame(frame, text="Search by Case")
        case_frame.pack(fill="x", padx=10, pady=5)
        self.case_type_entry = ttk.Entry(case_frame, width=10)
        self.case_type_entry.pack(side="left", padx=5, pady=5)
        self.case_no_entry = ttk.Entry(case_frame, width=10)
        self.case_no_entry.pack(side="left", padx=5, pady=5)
        self.case_year_entry = ttk.Entry(case_frame, width=10)
        self.case_year_entry.pack(side="left", padx=5, pady=5)
        ttk.Label(case_frame, text="Type  Number  Year").pack(side="left", padx=5)

        # Options
        options_frame = ttk.Frame(frame)
        options_frame.pack(fill="x", padx=10, pady=5)
        self.today_var = tk.BooleanVar()
        self.tomorrow_var = tk.BooleanVar()
        self.pdf_var = tk.BooleanVar()
        ttk.Checkbutton(options_frame, text="Today", variable=self.today_var).pack(side="left", padx=5)
        ttk.Checkbutton(options_frame, text="Tomorrow", variable=self.tomorrow_var).pack(side="left", padx=5)
        ttk.Checkbutton(options_frame, text="Download PDF", variable=self.pdf_var).pack(side="left", padx=5)

        ttk.Button(frame, text="Run Search", command=self.run_search).pack(pady=5)

        self.output_text = scrolledtext.ScrolledText(frame, wrap='word', height=20)
        self.output_text.pack(fill="both", padx=10, pady=5)

    def build_causelist_tab(self):
        frame = self.causelist_tab
        ttk.Label(frame, text="Download Entire Cause List (Today)").pack(pady=10)
        self.cl_out_path = tk.StringVar()
        ttk.Entry(frame, textvariable=self.cl_out_path, width=50).pack(side="left", padx=5, pady=5)
        ttk.Button(frame, text="Browse", command=self.browse_file).pack(side="left", padx=5)
        ttk.Button(frame, text="Download", command=self.download_causelist).pack(side="left", padx=5)

 
    def browse_file(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if path:
            self.cl_out_path.set(path)

    def run_search(self):
        self.output_text.delete(1.0, tk.END)
        output = {"query": {}, "results": None}
        cnr = self.cnr_entry.get().strip()
        case_type = self.case_type_entry.get().strip()
        number = self.case_no_entry.get().strip()
        year = self.case_year_entry.get().strip()

        try:
            if cnr:
                output["query"]["cnr"] = cnr
                res = search_by_cnr(cnr)
                output["results"] = res
                if self.today_var.get() or self.tomorrow_var.get():
                    date = datetime.date.today() if self.today_var.get() else datetime.date.today() + datetime.timedelta(days=1)
                    cl = get_cause_list_for_court(date=date)
                    output["cause_list_attempt"] = cl
                    if cl.get("ok") and cl.get("pdfs"):
                        pdf_url = cl["pdfs"][0]
                        found = check_listing_in_causelist(pdf_url, {"cnr": cnr})
                        output["found_in_causelist"] = found
                if self.pdf_var.get() and res.get("info") and res["info"].get("pdf_links"):
                    os.makedirs("downloads", exist_ok=True)
                    for i, pdf in enumerate(res["info"]["pdf_links"]):
                        fname = os.path.join("downloads", f"{cnr}_doc_{i+1}.pdf")
                        download_file(pdf, fname)

            elif case_type and number and year:
                output["query"]["case_type"] = case_type
                output["query"]["number"] = number
                output["query"]["year"] = year
                res = search_by_case(case_type, number, year)
                output["results"] = res
                if self.today_var.get() or self.tomorrow_var.get():
                    date = datetime.date.today() if self.today_var.get() else datetime.date.today() + datetime.timedelta(days=1)
                    cl = get_cause_list_for_court(date=date)
                    output["cause_list_attempt"] = cl
            else:
                messagebox.showerror("Input Error", "Enter either CNR or Case Type/Number/Year")
                return

            self.output_text.insert(tk.END, json.dumps(output, indent=2))
        except Exception as e:
            messagebox.showerror("Error", str(e))


    def download_causelist(self):
        path = self.cl_out_path.get()
        if not path:
            messagebox.showwarning("Output Path", "Select an output file path first!")
            return
        cl = get_cause_list_for_court(date=datetime.date.today())
        write_json(path, cl)
        messagebox.showinfo("Done", f"Cause list saved -> {path}")

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    root = tk.Tk()
    app = ECourtsGUI(root)
    root.mainloop()
