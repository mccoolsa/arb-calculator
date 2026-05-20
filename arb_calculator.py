import customtkinter as ctk
import csv
from datetime import datetime
from tkinter import messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

def parse_odds(odds_str):
    if not odds_str:
        return None
    if '/' in odds_str:
        try:
            num, den = map(float, odds_str.split('/'))
            return (num / den) + 1
        except ValueError:
            return None
    try:
        return float(odds_str)
    except ValueError:
        return None

class ArbitrageApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ARBITRAGE FINAL BOSS")
        self.geometry("1250x950")
        self.configure(fg_color="#0b1710")

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- TOP CONTROL BAR ---
        self.control_frame = ctk.CTkFrame(self, fg_color="#122a1b", corner_radius=15, border_width=2, border_color="#1e4a2f")
        self.control_frame.pack(pady=20, padx=20, fill="x")

        self.header_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(20, 10))

        self.title_label = ctk.CTkLabel(self.header_frame, text="ARBITRAGE FINAL BOSS", font=("Helvetica", 24, "bold", "italic"), text_color="#34d399")
        self.title_label.pack(side="left", padx=(0, 40))

        self.inv_label = ctk.CTkLabel(self.header_frame, text="Total Stake:", font=("Helvetica", 14, "bold"), text_color="#a7f3d0")
        self.inv_label.pack(side="left", padx=(0, 10))
        
        self.inv_entry = ctk.CTkEntry(self.header_frame, placeholder_text="e.g. 100", width=120, border_color="#34d399")
        self.inv_entry.pack(side="left", padx=0)

        self.use_defaults_var = ctk.BooleanVar(value=True)
        self.default_cb = ctk.CTkCheckBox(self.header_frame, text="Default Names", 
                                          variable=self.use_defaults_var, command=self.toggle_name_inputs,
                                          fg_color="#059669", hover_color="#10b981", text_color="#a7f3d0", font=("Helvetica", 14, "bold"))
        self.default_cb.pack(side="left", padx=40)

        self.error_label = ctk.CTkLabel(self.header_frame, text="", text_color="#ef4565", font=("Helvetica", 14, "bold"))
        self.error_label.pack(side="left", padx=10)

        # Column Headers
        self.col_headers_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.col_headers_frame.pack(fill="x", padx=20, pady=(10, 0))
        
        ctk.CTkLabel(self.col_headers_frame, text="", width=60).pack(side="left", padx=5)
        
        self.name_header = ctk.CTkLabel(self.col_headers_frame, text="Custom Name", width=120, text_color="#6ee7b7", font=("Helvetica", 13, "bold"))
        self.name_header.pack(side="left", padx=5)
        self.name_header.pack_forget() 
        
        # FIX: Assigned the Odds header to 'self' so we can reference it properly when repacking the name header
        self.odds_header = ctk.CTkLabel(self.col_headers_frame, text="Enter Odds", width=150, text_color="#6ee7b7", font=("Helvetica", 13, "bold"))
        self.odds_header.pack(side="left", padx=5)
        
        ctk.CTkLabel(self.col_headers_frame, text="Calculated Stake", width=150, text_color="#6ee7b7", font=("Helvetica", 13, "bold")).pack(side="left", padx=30)
        ctk.CTkLabel(self.col_headers_frame, text="Potential Payout", width=150, text_color="#6ee7b7", font=("Helvetica", 13, "bold")).pack(side="left", padx=10)

        self.rows_container = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.rows_container.pack(fill="x", padx=20, pady=5)

        self.bet_rows = []
        
        for _ in range(4):
            self.add_row()

        self.action_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.action_frame.pack(fill="x", padx=20, pady=20)

        self.add_btn = ctk.CTkButton(self.action_frame, text="+ ADD ROW", command=self.add_row, width=100, fg_color="#059669", hover_color="#10b981", font=("Helvetica", 12, "bold"))
        self.add_btn.pack(side="left", padx=(0, 10))

        self.rem_btn = ctk.CTkButton(self.action_frame, text="- REMOVE ROW", command=self.remove_row, width=100, fg_color="#991b1b", hover_color="#dc2626", font=("Helvetica", 12, "bold"))
        self.rem_btn.pack(side="left", padx=10)

        self.reset_btn = ctk.CTkButton(self.action_frame, text="↺ RESET", command=self.reset_fields, width=100, fg_color="transparent", border_width=2, border_color="#34d399", hover_color="#064e3b", font=("Helvetica", 12, "bold"))
        self.reset_btn.pack(side="left", padx=10)

        self.calc_btn = ctk.CTkButton(self.action_frame, text="CALCULATE", command=self.calculate, width=200, height=40, fg_color="#f59e0b", hover_color="#d97706", text_color="#000000", font=("Helvetica", 16, "bold"))
        self.calc_btn.pack(side="right", padx=10)

        self.results_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.results_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.results_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.result_cards = []

    def toggle_name_inputs(self):
        use_default = self.use_defaults_var.get()
        
        if use_default:
            self.name_header.pack_forget()
        else:
            # FIX: We now pack the name_header specifically before the odds_header which shares the same parent frame
            self.name_header.pack(side="left", padx=5, before=self.odds_header)

        for row in self.bet_rows:
            if use_default:
                row['name_entry'].grid_remove()
            else:
                row['name_entry'].grid()

    def add_row(self):
        idx = len(self.bet_rows)
        row_frame = ctk.CTkFrame(self.rows_container, fg_color="transparent")
        row_frame.pack(fill="x", pady=5)

        row_label = ctk.CTkLabel(row_frame, text=f"Bet {idx+1}", width=60, font=("Helvetica", 14, "bold"), text_color="#a7f3d0")
        row_label.grid(row=0, column=0, padx=5)

        name_entry = ctk.CTkEntry(row_frame, placeholder_text="Custom Name", width=120)
        name_entry.grid(row=0, column=1, padx=5)
        if self.use_defaults_var.get():
            name_entry.grid_remove()

        odds_entry = ctk.CTkEntry(row_frame, placeholder_text="Odds", width=150)
        odds_entry.grid(row=0, column=2, padx=5)

        stake_display = ctk.CTkLabel(row_frame, text="€0.00", width=150, fg_color="#064e3b", corner_radius=5, font=("Helvetica", 14, "bold"))
        stake_display.grid(row=0, column=3, padx=30)

        payout_display = ctk.CTkLabel(row_frame, text="€0.00", width=150, fg_color="#064e3b", corner_radius=5, font=("Helvetica", 14, "bold"))
        payout_display.grid(row=0, column=4, padx=10)

        self.bet_rows.append({
            'frame': row_frame,
            'row_label': row_label,
            'name_entry': name_entry,
            'odds_entry': odds_entry,
            'stake_val': stake_display,
            'payout_val': payout_display,
            'index': idx
        })

    def remove_row(self):
        if len(self.bet_rows) > 2:
            row_dict = self.bet_rows.pop()
            row_dict['frame'].destroy()

    def reset_fields(self):
        self.inv_entry.delete(0, 'end')
        self.error_label.configure(text="")
        for row in self.bet_rows:
            row['odds_entry'].delete(0, 'end')
            row['stake_val'].configure(text="€0.00", text_color="#ffffff")
            row['payout_val'].configure(text="€0.00", text_color="#ffffff")

    def calculate(self):
        self.error_label.configure(text="")
        
        try:
            investment = float(self.inv_entry.get())
        except ValueError:
            self.error_label.configure(text="Invalid Total Stake!")
            return

        valid_rows = []
        parsed_odds = []
        final_names = []

        for row in self.bet_rows:
            odds_str = row['odds_entry'].get()
            if odds_str.strip():
                val = parse_odds(odds_str)
                if val:
                    valid_rows.append(row)
                    parsed_odds.append(val)
                    
                    if self.use_defaults_var.get() or not row['name_entry'].get().strip():
                        final_names.append(f"Bet {row['index']+1}")
                    else:
                        final_names.append(row['name_entry'].get().strip())
                else:
                    self.error_label.configure(text=f"Invalid odds format: {odds_str}")
                    return
            else:
                row['stake_val'].configure(text="€0.00", text_color="#ffffff")
                row['payout_val'].configure(text="€0.00", text_color="#ffffff")

        if len(parsed_odds) < 2:
            self.error_label.configure(text="Enter at least 2 valid odds!")
            return

        implied_probs = [1 / o for o in parsed_odds]
        margin = sum(implied_probs)

        if margin == 0:
            return

        payout = investment / margin
        profit = payout - investment
        roi = (profit / investment) * 100
        stakes = [(payout / o) for o in parsed_odds]

        if margin < 1:
            color = "#34d399" 
            status_text = "🟢 ARBITRAGE FOUND"
            status_csv = "Arb Found"
        else:
            color = "#ef4565"
            status_text = "🔴 NEGATIVE ROI"
            status_csv = "Negative ROI"

        for i, row in enumerate(valid_rows):
            row['stake_val'].configure(text=f"€{stakes[i]:.2f}", text_color=color)
            row['payout_val'].configure(text=f"€{payout:.2f}", text_color=color)

        card_data = {
            "status": status_csv,
            "investment": investment,
            "payout": payout,
            "profit": profit,
            "roi": roi,
            "names": final_names,
            "odds": parsed_odds,
            "stakes": stakes
        }

        res_text = f"{status_text}\n\n"
        res_text += f"ROI:       {roi:+.2f}%\n"
        res_text += f"Profit:    €{profit:+.2f}\n"
        res_text += f"Total Rtn: €{payout:.2f}\n"
        res_text += f"{'-'*25}\n"
        for i, s in enumerate(stakes):
            res_text += f"{final_names[i][:8]} (@{parsed_odds[i]:.2f}): €{s:.2f}\n"

        self.create_result_card(res_text, color, card_data)

    def create_result_card(self, text, color, card_data):
        card_frame = ctk.CTkFrame(self.results_frame, fg_color="#122a1b", border_color=color, border_width=2, corner_radius=10)
        
        header = ctk.CTkFrame(card_frame, fg_color="transparent")
        header.pack(fill="x", padx=5, pady=5)

        card_dict = {"frame": card_frame, "data": card_data}
        
        close_btn = ctk.CTkButton(header, text="X", width=25, height=25, fg_color="transparent", 
                                  hover_color="#ef4565", text_color="#a7f3d0", 
                                  command=lambda d=card_dict: self.remove_card(d))
        close_btn.pack(side="right")

        box = ctk.CTkTextbox(card_frame, height=180, width=250, fg_color="transparent", text_color=color, font=("Courier", 14, "bold"))
        box.pack(padx=10, pady=(0, 10))
        box.insert("1.0", text)
        box.configure(state="disabled")

        self.result_cards.append(card_dict)
        self.refresh_grid()

    def remove_card(self, card_dict):
        card_dict["frame"].destroy()
        self.result_cards.remove(card_dict)
        self.refresh_grid()

    def refresh_grid(self):
        for card in self.result_cards:
            card["frame"].grid_forget()
        
        for i, card in enumerate(self.result_cards):
            row = i // 4
            col = i % 4
            card["frame"].grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

    def on_closing(self):
        count = len(self.result_cards)
        if count > 0:
            if messagebox.askyesno("Save Results", f"You have {count} active results.\n\nDo you want to save them to a CSV file before exiting?"):
                
                date_str = datetime.now().strftime("%Y-%m-%d")
                filename = f"ArbCalc{count}_{date_str}.csv"
                
                try:
                    with open(filename, mode='w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        
                        max_legs = max([len(item["data"]["odds"]) for item in self.result_cards])
                        
                        header = ["Status", "Total Stake", "Total Return", "Profit", "ROI (%)"]
                        for i in range(max_legs):
                            header.extend([f"Sel {i+1} Name", f"Sel {i+1} Odds", f"Sel {i+1} Stake"])
                        
                        writer.writerow(header)
                        
                        for item in self.result_cards:
                            d = item["data"]
                            row = [
                                d["status"], f"{d['investment']:.2f}", f"{d['payout']:.2f}", 
                                f"{d['profit']:.2f}", f"{d['roi']:.2f}"
                            ]
                            
                            for i in range(max_legs):
                                if i < len(d["odds"]):
                                    row.extend([d["names"][i], f"{d['odds'][i]:.2f}", f"{d['stakes'][i]:.2f}"])
                                else:
                                    row.extend(["", "", ""]) 
                                    
                            writer.writerow(row)
                            
                except Exception as e:
                    messagebox.showerror("Export Error", f"Could not save the file:\n{e}")

        self.destroy()

if __name__ == "__main__":
    app = ArbitrageApp()
    app.mainloop()