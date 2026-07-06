import re
import math
import threading
import webbrowser
import requests
from bs4 import BeautifulSoup
import tkinter as tk
import customtkinter as ctk

# =========================================================
#  RUNNING MAN INDEX — Premium Glass Edition
#  Segoe UI typography · Glassmorphism cards · Animated
#  spinner · Hover transitions · Staggered entrance
# =========================================================

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

FONT = "Segoe UI"

# --- Palette: premium charcoal + Running Man signature yellow ---
COL_BG          = "#0D0F12"
COL_BG_GLOW     = "#14171B"
COL_GLASS       = "#1C2026"
COL_GLASS_EDGE  = "#2E333B"
COL_GLASS_ALT   = "#22262D"
COL_ACCENT      = "#F5C518"
COL_ACCENT_HL   = "#FFE066"
COL_ACCENT_DK   = "#B98F0C"
COL_TEXT        = "#F5F6F7"
COL_SUBTEXT     = "#8B929B"
COL_SUCCESS     = "#3DDC84"
COL_ERROR       = "#FF5C6C"
COL_INFO        = "#5CA9FF"
COL_CHIP_BG     = "#262B32"

HEADERS = {"User-Agent": "RunningManModernGUI/5.0"}
GITHUB_URL = "https://github.com/Nyein-Htut"


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\[.*?\]", "", text).strip()


def get_year_for_episode(ep_num):
    if ep_num <= 23: return "2010"
    elif ep_num <= 74: return "2011"
    elif ep_num <= 126: return "2012"
    elif ep_num <= 178: return "2013"
    elif ep_num <= 227: return "2014"
    elif ep_num <= 279: return "2015"
    elif ep_num <= 331: return "2016"
    elif ep_num <= 383: return "2017"
    elif ep_num <= 432: return "2018"
    elif ep_num <= 483: return "2019"
    elif ep_num <= 535: return "2020"
    elif ep_num <= 585: return "2021"
    elif ep_num <= 634: return "2022"
    elif ep_num <= 686: return "2023"
    elif ep_num <= 734: return "2024"
    elif ep_num <= 783: return "2025"
    else: return "2026"


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


def lerp_color(c1, c2, t):
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return rgb_to_hex((r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t))


# =========================================================
#  ANIMATED HOVER BUTTON — smooth color transition on hover
# =========================================================
class GlowButton(ctk.CTkButton):
    def __init__(self, master, base_color, hover_color, text_col_base, **kwargs):
        super().__init__(
            master,
            fg_color=base_color,
            hover=False,  # we handle hover manually for smooth animation
            text_color=text_col_base,
            **kwargs,
        )
        self._base = base_color
        self._hover = hover_color
        self._steps = 8
        self._job = None
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _animate(self, start, end, i):
        if i > self._steps:
            return
        t = i / self._steps
        self.configure(fg_color=lerp_color(start, end, t))
        self._job = self.after(12, lambda: self._animate(start, end, i + 1))

    def _on_enter(self, _e):
        if self._job:
            self.after_cancel(self._job)
        self._animate(self._base, self._hover, 0)

    def _on_leave(self, _e):
        if self._job:
            self.after_cancel(self._job)
        self._animate(self._hover, self._base, 0)


# =========================================================
#  ANIMATED LOADING SPINNER (canvas arc rotation)
# =========================================================
class Spinner(ctk.CTkFrame):
    def __init__(self, master, size=34, color=COL_ACCENT, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.size = size
        self.canvas = tk.Canvas(
            self, width=size, height=size, bg=COL_BG, highlightthickness=0
        )
        self.canvas.pack()
        self.color = color
        self.angle = 0
        self._running = False
        self._job = None

    def _sync_bg(self):
        try:
            parent_color = self.master.cget("fg_color")
            if isinstance(parent_color, tuple):
                parent_color = parent_color[-1]
            self.canvas.configure(bg=parent_color)
        except Exception:
            pass

    def start(self):
        self._sync_bg()
        self._running = True
        self._spin()

    def stop(self):
        self._running = False
        if self._job:
            self.after_cancel(self._job)
        self.canvas.delete("all")

    def _spin(self):
        if not self._running:
            return
        self.canvas.delete("all")
        pad = 4
        self.canvas.create_arc(
            pad, pad, self.size - pad, self.size - pad,
            start=self.angle, extent=110,
            style="arc", outline=self.color, width=4,
        )
        self.angle = (self.angle - 14) % 360
        self._job = self.after(35, self._spin)


# =========================================================
#  MAIN APPLICATION
# =========================================================
class RunningManApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Running Man Data Finder")
        self.geometry("720x800")
        self.minsize(720, 800)
        self.configure(fg_color=COL_BG)

        self._build_header()
        self._build_search_panel()
        self._build_status_row()
        self._build_results_area()
        self._build_footer()

        self.display_placeholders()

    # -----------------------------------------------------
    # HEADER
    # -----------------------------------------------------
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=COL_BG_GLOW, corner_radius=0, height=150)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        glow_strip = ctk.CTkFrame(header, fg_color=COL_ACCENT, height=3, corner_radius=0)
        glow_strip.pack(fill="x", side="bottom")

        badge = ctk.CTkFrame(header, fg_color=COL_GLASS, corner_radius=18, width=60, height=60,
                              border_width=1, border_color=COL_ACCENT)
        badge.place(relx=0.5, rely=0.32, anchor="center")
        ctk.CTkLabel(badge, text="🏃", font=ctk.CTkFont(size=26)).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            header,
            text="RUNNING MAN INDEX",
            font=ctk.CTkFont(family=FONT, size=27, weight="bold"),
            text_color=COL_TEXT,
        ).place(relx=0.5, rely=0.64, anchor="center")

        ctk.CTkLabel(
            header,
            text="Live episode records — straight from the archives",
            font=ctk.CTkFont(family=FONT, size=12),
            text_color=COL_SUBTEXT,
        ).place(relx=0.5, rely=0.86, anchor="center")

    # -----------------------------------------------------
    # SEARCH PANEL (glass card)
    # -----------------------------------------------------
    def _build_search_panel(self):
        body = ctk.CTkFrame(self, fg_color=COL_BG, corner_radius=0)
        body.pack(fill="both", expand=True, padx=28, pady=(22, 0))
        self.body = body

        search_card = ctk.CTkFrame(
            body, fg_color=COL_GLASS, corner_radius=18,
            border_width=1, border_color=COL_GLASS_EDGE,
        )
        search_card.pack(fill="x", pady=(0, 18))

        inner = ctk.CTkFrame(search_card, fg_color="transparent")
        inner.pack(pady=22, padx=22, fill="x")

        ctk.CTkLabel(
            inner, text="EPISODE LOOKUP",
            font=ctk.CTkFont(family=FONT, size=11, weight="bold"),
            text_color=COL_ACCENT,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        self.entry = ctk.CTkEntry(
            inner,
            placeholder_text="Enter episode number, e.g. 387",
            width=380,
            height=48,
            corner_radius=12,
            font=ctk.CTkFont(family=FONT, size=15),
            fg_color=COL_GLASS_ALT,
            border_width=1,
            border_color=COL_GLASS_EDGE,
            text_color=COL_TEXT,
        )
        self.entry.grid(row=1, column=0, padx=(0, 12), sticky="ew")
        self.entry.bind("<Return>", lambda e: self.start_search())
        self.entry.bind("<FocusIn>", lambda e: self.entry.configure(border_color=COL_ACCENT))
        self.entry.bind("<FocusOut>", lambda e: self.entry.configure(border_color=COL_GLASS_EDGE))

        self.search_btn = GlowButton(
            inner,
            base_color=COL_ACCENT,
            hover_color=COL_ACCENT_HL,
            text_col_base=COL_BG,
            text="🔍  Search",
            width=150,
            height=48,
            corner_radius=12,
            font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
            command=self.start_search,
        )
        self.search_btn.grid(row=1, column=1)

        inner.grid_columnconfigure(0, weight=1)

    # -----------------------------------------------------
    # STATUS ROW (status text + spinner)
    # -----------------------------------------------------
    def _build_status_row(self):
        row = ctk.CTkFrame(self.body, fg_color="transparent", height=30)
        row.pack(fill="x", pady=(0, 12))

        self.spinner = Spinner(row, size=20)
        self.spinner.pack(side="left", padx=(4, 8))
        self.spinner.pack_forget()  # hidden until searching

        self.status_dot = ctk.CTkLabel(row, text="●", font=ctk.CTkFont(size=13), text_color=COL_SUBTEXT)
        self.status_dot.pack(side="left", padx=(4, 6))

        self.status_label = ctk.CTkLabel(
            row, text="Ready to search",
            font=ctk.CTkFont(family=FONT, size=13),
            text_color=COL_SUBTEXT,
        )
        self.status_label.pack(side="left")

        self.status_row = row

    # -----------------------------------------------------
    # RESULTS AREA
    # -----------------------------------------------------
    def _build_results_area(self):
        self.result_card = ctk.CTkScrollableFrame(
            self.body,
            fg_color=COL_GLASS,
            corner_radius=18,
            border_width=1,
            border_color=COL_GLASS_EDGE,
            scrollbar_button_color=COL_ACCENT_DK,
            scrollbar_button_hover_color=COL_ACCENT,
        )
        self.result_card.pack(fill="both", expand=True, pady=(0, 14))

    # -----------------------------------------------------
    # FOOTER
    # -----------------------------------------------------
    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color=COL_BG, corner_radius=0, height=44)
        footer.pack(fill="x", side="bottom", pady=(0, 12))

        footer_lbl = ctk.CTkLabel(
            footer,
            text="© 2026 Built by Irene (Nyein Htut Tin)  •  github.com/Nyein-Htut",
            font=ctk.CTkFont(family=FONT, size=11),
            text_color=COL_SUBTEXT,
            cursor="hand2",
        )
        footer_lbl.pack(pady=10)
        footer_lbl.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL))
        footer_lbl.bind("<Enter>", lambda e: footer_lbl.configure(text_color=COL_ACCENT))
        footer_lbl.bind("<Leave>", lambda e: footer_lbl.configure(text_color=COL_SUBTEXT))

    # =====================================================
    # UI STATE HELPERS
    # =====================================================
    def display_placeholders(self):
        self.clear_result_card()
        wrap = ctk.CTkFrame(self.result_card, fg_color="transparent")
        wrap.pack(expand=True, pady=140)

        ctk.CTkLabel(wrap, text="🎯", font=ctk.CTkFont(size=42)).pack(pady=(0, 12))
        ctk.CTkLabel(
            wrap,
            text="Waiting for input...\nType an episode number above to fetch its record.",
            font=ctk.CTkFont(family=FONT, size=14),
            text_color=COL_SUBTEXT,
            justify="center",
        ).pack()

    def clear_result_card(self):
        for widget in self.result_card.winfo_children():
            widget.destroy()

    def set_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)
        self.status_dot.configure(text_color=color)

    # =====================================================
    # SEARCH LOGIC
    # =====================================================
    def start_search(self):
        raw_val = self.entry.get().strip()
        if not raw_val.isdigit():
            self.set_status("Please enter a valid episode number", COL_ERROR)
            return

        self.set_status("Querying archives...", COL_INFO)
        self.search_btn.configure(state="disabled", text="Searching...")
        self.spinner.pack(side="left", padx=(4, 8), before=self.status_dot)
        self.spinner.start()

        threading.Thread(target=self.execute_network_crawl, args=(int(raw_val),), daemon=True).start()

    def execute_network_crawl(self, ep_num):
        year = get_year_for_episode(ep_num)
        url = f"https://en.wikipedia.org/wiki/List_of_Running_Man_episodes_({year})"
        data = None

        try:
            res = requests.get(url, headers=HEADERS, timeout=7)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for table in soup.find_all("table", class_="wikitable"):
                    for row in table.find_all("tr"):
                        th_cells = row.find_all("th")
                        td_cells = row.find_all("td")

                        if th_cells and len(td_cells) >= 4:
                            if clean_text(th_cells[0].text) == str(ep_num):
                                data = {
                                    "Episode": clean_text(th_cells[0].text),
                                    "Year": year,
                                    "Air Date": clean_text(td_cells[0].text),
                                    "Title": clean_text(td_cells[1].text),
                                    "Guest(s)": clean_text(td_cells[2].text),
                                    "Teams": clean_text(td_cells[3].text),
                                    "Mission": clean_text(td_cells[4].text) if len(td_cells) > 4 else "N/A",
                                    "Results": clean_text(td_cells[5].text) if len(td_cells) > 5 else "N/A",
                                }
                                break
        except Exception:
            pass

        self.after(0, lambda: self.render_ui_results(data, ep_num))

    # =====================================================
    # RESULTS RENDERING (with staggered entrance animation)
    # =====================================================
    def render_ui_results(self, data, ep_num):
        self.search_btn.configure(state="normal", text="🔍  Search")
        self.spinner.stop()
        self.spinner.pack_forget()
        self.clear_result_card()

        if not data:
            self.set_status("No match found", COL_ERROR)
            wrap = ctk.CTkFrame(self.result_card, fg_color="transparent")
            wrap.pack(expand=True, pady=140)
            ctk.CTkLabel(wrap, text="🚫", font=ctk.CTkFont(size=42)).pack(pady=(0, 12))
            ctk.CTkLabel(
                wrap,
                text=f"No database entry found for Episode {ep_num}.\nDouble-check the number or your internet connection.",
                font=ctk.CTkFont(family=FONT, size=14),
                text_color=COL_ERROR,
                justify="center",
            ).pack()
            return

        self.set_status("Data retrieved successfully", COL_SUCCESS)

        # --- Title banner (glass) ---
        banner = ctk.CTkFrame(
            self.result_card, fg_color=COL_GLASS_ALT, corner_radius=16,
            border_width=1, border_color=COL_GLASS_EDGE,
        )
        banner.pack(fill="x", pady=(8, 14), padx=6)

        ctk.CTkLabel(
            banner, text=f"EPISODE {data['Episode']}",
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            text_color=COL_ACCENT,
        ).pack(anchor="w", padx=20, pady=(16, 4))

        ctk.CTkLabel(
            banner, text=data["Title"],
            font=ctk.CTkFont(family=FONT, size=20, weight="bold"),
            text_color=COL_TEXT, wraplength=580, justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 12))

        # --- Statistics chips ---
        chip_row = ctk.CTkFrame(banner, fg_color="transparent")
        chip_row.pack(anchor="w", padx=20, pady=(0, 18))

        guest_count = len([g for g in data["Guest(s)"].split(",") if g.strip()]) or 1
        chips = [
            ("📅", data["Year"]),
            ("🎤", f"{guest_count} Guest{'s' if guest_count != 1 else ''}"),
            ("📺", f"Ep. {data['Episode']}"),
        ]
        for emoji, text in chips:
            chip = ctk.CTkFrame(chip_row, fg_color=COL_CHIP_BG, corner_radius=20,
                                 border_width=1, border_color=COL_GLASS_EDGE)
            chip.pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                chip, text=f"{emoji}  {text}",
                font=ctk.CTkFont(family=FONT, size=11, weight="bold"),
                text_color=COL_TEXT,
            ).pack(padx=14, pady=6)

        # --- Data fields (staggered entrance) ---
        fields = [
            ("📅", "Air Date"),
            ("🎤", "Guest(s)"),
            ("👥", "Teams"),
            ("🎯", "Mission"),
            ("🏆", "Results"),
        ]

        self._stagger_rows(fields, data, 0)

    def _stagger_rows(self, fields, data, index):
        if index >= len(fields):
            return

        emoji, field = fields[index]

        row_frame = ctk.CTkFrame(
            self.result_card,
            fg_color=COL_GLASS_ALT if index % 2 == 0 else "transparent",
            corner_radius=12,
            border_width=1,
            border_color=COL_ACCENT,  # starts highlighted, then fades
        )
        row_frame.pack(fill="x", pady=5, padx=6)

        inner = ctk.CTkFrame(row_frame, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(
            inner, text=f"{emoji}  {field}",
            font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
            text_color=COL_ACCENT, width=150, anchor="w",
        ).pack(side="left", anchor="n")

        ctk.CTkLabel(
            inner, text=data[field],
            font=ctk.CTkFont(family=FONT, size=13),
            text_color=COL_TEXT, wraplength=380, justify="left", anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # fade the highlight border back to normal after a beat
        self.after(220, lambda: self._fade_border(row_frame, 0))

        # schedule the next row with a staggered delay
        self.after(90, lambda: self._stagger_rows(fields, data, index + 1))

    def _fade_border(self, widget, step, total=6):
        if step > total:
            widget.configure(border_color=COL_GLASS_EDGE)
            return
        t = step / total
        widget.configure(border_color=lerp_color(COL_ACCENT, COL_GLASS_EDGE, t))
        self.after(30, lambda: self._fade_border(widget, step + 1, total))


if __name__ == "__main__":
    app = RunningManApp()
    app.mainloop()