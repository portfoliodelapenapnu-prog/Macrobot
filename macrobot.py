import sys
import time
import json
import threading
import os
import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import customtkinter as ctk
from pynput import mouse, keyboard
import pyautogui
import cv2
import numpy as np
from PIL import Image, ImageTk

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ==========================================================
# SCREEN OVERLAY: TRANSPARENT SNIPPER
# ==========================================================
class ScreenSnipperOverlay(tk.Toplevel):
    """Transparent full-screen snipper using global pynput input.

    This overlay uses a lightweight transparent fullscreen window while
    listening for global mouse and keyboard events, which is more stable
    across Windows and multi-monitor setups.
    """
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.mouse_listener = None
        self.keyboard_listener = None
        self.start_x = None
        self.start_y = None
        self.rect = None
        self._selection_active = False

        # Fullscreen, topmost, and borderless setup
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        try:
            self.overrideredirect(True)
        except Exception:
            pass
        self.attributes("-alpha", 0.25)
        self.config(bg="black", cursor="cross")

        self.canvas = tk.Canvas(self, cursor="cross", bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(self.winfo_screenwidth() // 2, 30,
                                text="Click once for start, move, then release to capture — press ESC to cancel",
                                fill="#CDD6F4", font=("Segoe UI", 12, "bold"))

        self.after(100, self.ensure_focus)
        self.after(150, self.start_global_listeners)

    def ensure_focus(self):
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:
            pass

    def start_global_listeners(self):
        try:
            def on_move(x, y):
                try:
                    self.after(0, lambda: self._on_mouse_move(x, y))
                except Exception:
                    pass

            def on_click(x, y, button, pressed):
                if button != mouse.Button.left:
                    return
                try:
                    if pressed:
                        self.after(0, lambda: self._on_mouse_press(x, y))
                    else:
                        self.after(0, lambda: self._on_mouse_release(x, y))
                except Exception:
                    pass

            def on_key_press(key):
                if key == keyboard.Key.esc:
                    try:
                        self.after(0, self.exit_safely)
                    except Exception:
                        pass

            self.mouse_listener = mouse.Listener(on_move=on_move, on_click=on_click)
            self.mouse_listener.start()
            self.keyboard_listener = keyboard.Listener(on_press=on_key_press)
            self.keyboard_listener.start()
        except Exception:
            self.mouse_listener = None
            self.keyboard_listener = None

    def _on_mouse_press(self, x, y):
        if self._selection_active:
            return
        self._selection_active = True
        self.start_x = int(x)
        self.start_y = int(y)
        lx = self.start_x - self.winfo_rootx()
        ly = self.start_y - self.winfo_rooty()
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(lx, ly, lx, ly, outline="#F38BA8", width=2)

    def _on_mouse_move(self, x, y):
        if not self._selection_active or self.start_x is None or self.start_y is None:
            return
        cur_x = int(x)
        cur_y = int(y)
        lx1 = self.start_x - self.winfo_rootx()
        ly1 = self.start_y - self.winfo_rooty()
        lx2 = cur_x - self.winfo_rootx()
        ly2 = cur_y - self.winfo_rooty()
        if self.rect:
            try:
                self.canvas.coords(self.rect, lx1, ly1, lx2, ly2)
            except Exception:
                pass

    def _on_mouse_release(self, x, y):
        if not self._selection_active or self.start_x is None or self.start_y is None:
            self.exit_safely()
            return

        end_x = int(x)
        end_y = int(y)
        x1 = int(min(self.start_x, end_x))
        y1 = int(min(self.start_y, end_y))
        x2 = int(max(self.start_x, end_x))
        y2 = int(max(self.start_y, end_y))

        width = x2 - x1
        height = y2 - y1

        self._selection_active = False
        if width > 5 and height > 5:
            os.makedirs("snips", exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = os.path.join("snips", f"snip_{ts}.png")
            try:
                img = pyautogui.screenshot(region=(x1, y1, width, height))
                img.save(path)
            except Exception:
                path = None
            self.exit_safely()
            try:
                self.callback(x1, y1, width, height, path)
            except TypeError:
                self.callback(x1, y1, width, height)
        else:
            self.exit_safely()

    def exit_safely(self):
        try:
            if self.mouse_listener:
                self.mouse_listener.stop()
                self.mouse_listener = None
        except Exception:
            pass
        try:
            if self.keyboard_listener:
                self.keyboard_listener.stop()
                self.keyboard_listener = None
        except Exception:
            pass
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


# ==========================================================
# VISUAL CONFIRMATION: FLASHES RED RECTANGLE AROUND TARGET
# ==========================================================
class VisualTargetHighlighter(tk.Toplevel):
    def __init__(self, x, y, width, height):
        super().__init__()
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-transparentcolor", "white")

        canvas = tk.Canvas(self, width=width, height=height, bg="white", highlightthickness=0)
        canvas.pack()
        canvas.create_rectangle(0, 0, width, height, outline="#F38BA8", width=4)

        self.after(1200, self.destroy)


# ==========================================================
# POP-UP MODAL: IMAGE DETECTION SPECIFICATIONS WINDOW
# ==========================================================
class ImageSearchConfigModal(ctk.CTkToplevel):
    def __init__(self, parent, callback, initial_payload=None):
        super().__init__(parent)
        self.title("Search Image Configuration")
        self.geometry("560x700")
        self.resizable(False, False)
        self.configure(fg_color="#1E1E2E")
        self.transient(parent)
        self.grab_set()

        self.parent = parent
        self.callback = callback
        self.selected_image_path = None
        self.tk_thumb = None
        self.search_region = None
        self.initial_payload = initial_payload

        self.setup_modal_ui()
        if initial_payload:
            self.load_initial_payload(initial_payload)

    def setup_modal_ui(self):
        title_lbl = ctk.CTkLabel(self, text="Finds position of the defined image in the selected screen area.", font=ctk.CTkFont(size=13, slant="italic"), text_color="#A6ADC8")
        title_lbl.pack(anchor="w", padx=20, pady=(15, 10))

        # --- CONTAINER 1: IMAGE SPECIFICATIONS ---
        self.spec_frame = ctk.CTkFrame(self, fg_color="#252538", border_color="#313244", border_width=1)
        self.spec_frame.pack(fill="x", padx=20, pady=5)
        
        lbl_sec1 = ctk.CTkLabel(self.spec_frame, text="Image specifications:", font=ctk.CTkFont(weight="bold", size=12), text_color="#CBA6F7")
        lbl_sec1.grid(row=0, column=0, columnspan=3, sticky="w", padx=15, pady=(10, 5))

        # Thumbnail Box
        self.thumb_canvas = tk.Canvas(self.spec_frame, width=140, height=100, bg="#13131F", highlightthickness=1, highlightbackground="#313244")
        self.thumb_canvas.grid(row=1, column=0, rowspan=4, padx=15, pady=(0, 15), sticky="nw")
        
        # Snipper Inputs
        self.btn_snip = ctk.CTkButton(self.spec_frame, text="📷 Drag Screenshot Selection", width=180, height=30, fg_color="#FAB387", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.trigger_template_snip)
        self.btn_snip.grid(row=1, column=1, columnspan=2, padx=(0, 15), pady=4, sticky="w")

        self.btn_browse = ctk.CTkButton(self.spec_frame, text="📁 Open Existing Image File", width=180, height=28, fg_color="#313244", hover_color="#45475A", command=self.browse_image)
        self.btn_browse.grid(row=2, column=1, columnspan=2, padx=(0, 15), pady=4, sticky="w")

        # Search Area Selector Dropdown Route
        lbl_area = ctk.CTkLabel(self.spec_frame, text="Define the search area:", font=ctk.CTkFont(size=11))
        lbl_area.grid(row=3, column=1, columnspan=2, padx=(0, 15), pady=(5, 0), sticky="w")
        
        self.combo_area = ctk.CTkOptionMenu(self.spec_frame, values=["Entire desktop", "Area of desktop", "Focused window", "Area of focused window"], width=180, fg_color="#13131F", button_color="#313244", command=self.toggle_define_button_visibility)
        self.combo_area.grid(row=4, column=1, padx=(0, 5), pady=(0, 10), sticky="w")

        # CONTEXTUAL "DEFINE" BUTTON
        self.btn_define_area = ctk.CTkButton(self.spec_frame, text="📍 Define", width=65, height=28, fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.trigger_area_perimeter_snip)
        self.btn_define_area.grid_forget()

        # PRE-STAGE ACTIONS FOR REVEAL LAYER MECHANICS
        self.lbl_tol = ctk.CTkLabel(self.spec_frame, text="Color tolerance:", font=ctk.CTkFont(size=11))
        self.tol_actions_frame = ctk.CTkFrame(self.spec_frame, fg_color="transparent")
        
        self.entry_tolerance = ctk.CTkEntry(self.tol_actions_frame, width=60, height=25, fg_color="#13131F", border_color="#313244")
        self.entry_tolerance.insert(0, "15")
        self.entry_tolerance.pack(side="left", padx=(0, 10))

        self.btn_test_match = ctk.CTkButton(self.tol_actions_frame, text="🔍 Test", width=80, height=25, fg_color="#89B4FA", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.test_live_image_match)
        self.btn_test_match.pack(side="left")

        # --- CONTAINER 2: IF IMAGE IS FOUND BRANCH ---
        found_frame = ctk.CTkFrame(self, fg_color="#252538", border_color="#313244", border_width=1)
        found_frame.pack(fill="x", padx=20, pady=5)

        lbl_sec2 = ctk.CTkLabel(found_frame, text="If image is found:", font=ctk.CTkFont(weight="bold", size=12), text_color="#A6E3A1")
        lbl_sec2.pack(anchor="w", padx=15, pady=(10, 5))

        f_row = ctk.CTkFrame(found_frame, fg_color="transparent")
        f_row.pack(fill="x", padx=15, pady=(0, 10))

        self.check_mouse = ctk.CTkCheckBox(f_row, text="Mouse action:", font=ctk.CTkFont(size=11), width=20)
        self.check_mouse.select()
        self.check_mouse.pack(side="left", padx=(0, 10))

        self.combo_action = ctk.CTkOptionMenu(f_row, values=["Positioning", "Left Click", "Right Click", "Hover Only"], width=110, height=25, fg_color="#13131F", button_color="#313244")
        self.combo_action.pack(side="left", padx=5)

        self.combo_pos = ctk.CTkOptionMenu(f_row, values=["Centered", "Top-Left", "Random Point"], width=110, height=25, fg_color="#13131F", button_color="#313244")
        self.combo_pos.pack(side="left", padx=5)

        f_branch_row = ctk.CTkFrame(found_frame, fg_color="transparent")
        f_branch_row.pack(fill="x", padx=15, pady=(0, 15))
        lbl_goto_f = ctk.CTkLabel(f_branch_row, text="Go to:", font=ctk.CTkFont(size=11))
        lbl_goto_f.pack(side="left", padx=(0, 10))
        self.combo_goto_found = ctk.CTkOptionMenu(f_branch_row, values=["Next", "Stop Macro", "Loop From Start"], width=140, height=25, fg_color="#13131F", button_color="#313244")
        self.combo_goto_found.pack(side="left")

        # --- CONTAINER 3: IF IMAGE IS NOT FOUND BRANCH ---
        not_found_frame = ctk.CTkFrame(self, fg_color="#252538", border_color="#313244", border_width=1)
        not_found_frame.pack(fill="x", padx=20, pady=5)

        lbl_sec3 = ctk.CTkLabel(not_found_frame, text="If image is not found:", font=ctk.CTkFont(weight="bold", size=12), text_color="#F38BA8")
        lbl_sec3.pack(anchor="w", padx=15, pady=(10, 5))

        nf_row1 = ctk.CTkFrame(not_found_frame, fg_color="transparent")
        nf_row1.pack(fill="x", padx=15, pady=(0, 10))
        lbl_wait_nf = ctk.CTkLabel(nf_row1, text="Continue waiting:", font=ctk.CTkFont(size=11))
        lbl_wait_nf.pack(side="left", padx=(0, 10))
        self.entry_wait = ctk.CTkEntry(nf_row1, width=50, height=25, fg_color="#13131F", border_color="#313244")
        self.entry_wait.insert(0, "120")
        self.entry_wait.pack(side="left", padx=5)
        lbl_secs = ctk.CTkLabel(nf_row1, text="seconds and then", font=ctk.CTkFont(size=11))
        lbl_secs.pack(side="left")

        nf_row2 = ctk.CTkFrame(not_found_frame, fg_color="transparent")
        nf_row2.pack(fill="x", padx=15, pady=(0, 15))
        lbl_goto_nf = ctk.CTkLabel(nf_row2, text="Go to:", font=ctk.CTkFont(size=11))
        lbl_goto_nf.pack(side="left", padx=(0, 10))
        self.combo_goto_notfound = ctk.CTkOptionMenu(nf_row2, values=["End", "Next", "Loop Retry Step"], width=140, height=25, fg_color="#13131F", button_color="#313244")
        self.combo_goto_notfound.pack(side="left")

        # --- FOOTER BUTTON LAYOUT ---
        footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer_frame.pack(fill="x", padx=20, pady=(10, 0), side="bottom")

        self.btn_ok = ctk.CTkButton(footer_frame, text="OK", width=95, fg_color="#A6E3A1", text_color="#11111B", font=ctk.CTkFont(weight="bold"), command=self.save_and_close)
        self.btn_ok.pack(side="right", padx=5, pady=10)

        self.btn_cancel = ctk.CTkButton(footer_frame, text="Cancel", width=95, fg_color="#585B70", text_color="white", command=self.destroy)
        self.btn_cancel.pack(side="right", padx=5, pady=10)

    def reveal_testing_tools(self):
        """Injects Tolerance sliders and Test matching tools directly when image data registers"""
        self.lbl_tol.grid(row=5, column=0, padx=15, pady=(5, 12), sticky="w")
        self.tol_actions_frame.grid(row=5, column=1, columnspan=2, padx=(0, 15), pady=(5, 12), sticky="w")

    def load_initial_payload(self, payload):
        if payload.get("path"):
            self.selected_image_path = payload["path"]
            try:
                img = Image.open(payload["path"])
                img.thumbnail((135, 95))
                self.tk_thumb = ImageTk.PhotoImage(img)
                self.thumb_canvas.delete("all")
                self.thumb_canvas.create_image(70, 50, image=self.tk_thumb)
            except Exception:
                pass
            self.reveal_testing_tools()

        if payload.get("search_area_mode"):
            try:
                self.combo_area.set(payload["search_area_mode"])
            except Exception:
                pass

        if payload.get("custom_region"):
            self.search_region = payload["custom_region"]
            self.toggle_define_button_visibility(payload.get("search_area_mode", "Area of desktop"))

        if payload.get("tolerance") is not None:
            self.entry_tolerance.delete(0, "end")
            self.entry_tolerance.insert(0, str(int(payload["tolerance"] * 100)))

        if payload.get("mouse_action_enabled") is False:
            self.check_mouse.deselect()
        else:
            self.check_mouse.select()

        if payload.get("action_type"):
            try:
                self.combo_action.set(payload["action_type"])
            except Exception:
                pass

        if payload.get("position_mode"):
            try:
                self.combo_pos.set(payload["position_mode"])
            except Exception:
                pass

        if payload.get("goto_found"):
            try:
                self.combo_goto_found.set(payload["goto_found"])
            except Exception:
                pass

        if payload.get("timeout_seconds") is not None:
            self.entry_wait.delete(0, "end")
            self.entry_wait.insert(0, str(payload["timeout_seconds"]))

        if payload.get("goto_notfound"):
            try:
                self.combo_goto_notfound.set(payload["goto_notfound"])
            except Exception:
                pass

    def toggle_define_button_visibility(self, value):
        if "Area" in value:
            self.btn_define_area.grid(row=4, column=2, padx=(5, 15), pady=(0, 10), sticky="w")
        else:
            self.btn_define_area.grid_forget()
            self.search_region = None

    def trigger_template_snip(self):
        try:
            self.grab_release()
        except Exception:
            pass
            
        self.withdraw()
        self.parent.withdraw()
        
        self.parent.update_idletasks()
        time.sleep(0.25)
        ScreenSnipperOverlay(None, self.on_template_snip_completed)

    def on_template_snip_completed(self, x, y, w, h, path=None):
        cache_path = path or f"template_cache_{int(time.time())}.png"
        if not path:
            try:
                screenshot = pyautogui.screenshot(region=(x, y, w, h))
                screenshot.save(cache_path)
            except Exception:
                pass
        
        self.selected_image_path = cache_path
        try:
            img = Image.open(cache_path)
            img.thumbnail((135, 95))
            self.tk_thumb = ImageTk.PhotoImage(img)
            self.thumb_canvas.delete("all")
            self.thumb_canvas.create_image(70, 50, image=self.tk_thumb)
        except Exception:
            pass
        
        self.parent.deiconify()
        self.deiconify()
        self.grab_set()
        self.reveal_testing_tools()

    def trigger_area_perimeter_snip(self):
        try:
            self.grab_release()
        except Exception:
            pass
            
        self.withdraw()
        self.parent.withdraw()
        
        self.parent.update_idletasks()
        time.sleep(0.25)
        ScreenSnipperOverlay(None, self.on_perimeter_snip_completed)

    def on_perimeter_snip_completed(self, x, y, w, h, path=None):
        self.search_region = (x, y, w, h)
        self.parent.deiconify()
        self.deiconify()
        self.grab_set()
        messagebox.showinfo("Area Defined", f"Scan Boundary Locked!\nOrigin: X:{x}, Y:{y}\nDimensions: {w}x{h} px")

    def browse_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png;*.jpg;*.jpeg")])
        if file_path:
            self.selected_image_path = file_path
            img = Image.open(file_path)
            img.thumbnail((135, 95))
            self.tk_thumb = ImageTk.PhotoImage(img)
            self.thumb_canvas.delete("all")
            self.thumb_canvas.create_image(70, 50, image=self.tk_thumb)
            self.reveal_testing_tools()

    def test_live_image_match(self):
        if not self.selected_image_path:
            messagebox.showwarning("Testing Error", "Please provide or snip a template target image first before running a test scan!")
            return

        area_mode = self.combo_area.get()
        if "Area" in area_mode and not self.search_region:
            messagebox.showwarning("Testing Error", "Please click 'Define' to map out your target search boundary box first!")
            return

        self.withdraw()
        self.parent.withdraw()
        self.parent.update_idletasks()
        time.sleep(0.25)

        if self.search_region:
            screen = pyautogui.screenshot(region=self.search_region)
            offset_x, offset_y = self.search_region[0], self.search_region[1]
        else:
            screen = pyautogui.screenshot()
            offset_x, offset_y = 0, 0

        screen_cv = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)
        template = cv2.imread(self.selected_image_path)

        if template is None:
            self.parent.deiconify()
            self.deiconify()
            self.grab_set()
            messagebox.showerror("Error", "Could not process image file template caching path data correctly.")
            return

        h, w, _ = template.shape
        res = cv2.matchTemplate(screen_cv, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        tolerance = float(self.entry_tolerance.get() or 0) / 100.0
        threshold = 1.0 - tolerance

        self.parent.deiconify()
        self.deiconify()
        self.grab_set()

        if max_val >= threshold:
            abs_x = offset_x + max_loc[0]
            abs_y = offset_y + max_loc[1]
            
            VisualTargetHighlighter(abs_x, abs_y, w, h)
            messagebox.showinfo("Match Found!", f"Target located successfully!\nMatch accuracy: {max_val:.2%}\nCoordinates: X:{abs_x}, Y:{abs_y}")
        else:
            messagebox.showwarning("No Match Found", f"Failed to detect target image with current parameters.\nBest confidence found was only: {max_val:.2%}\nRequired minimum target threshold score: {threshold:.2%}")

    def save_and_close(self):
        if not self.selected_image_path:
            messagebox.showwarning("Validation Error", "Please provide a screen target image using file or selection!")
            return
        
        area_mode = self.combo_area.get()
        if "Area" in area_mode and not self.search_region:
            messagebox.showwarning("Validation Error", "Please click 'Define' to map out your target search boundary box first!")
            return

        payload = {
            "path": self.selected_image_path,
            "tolerance": float(self.entry_tolerance.get() or 0) / 100.0,
            "mouse_action_enabled": self.check_mouse.get(),
            "action_type": self.combo_action.get(),
            "position_mode": self.combo_pos.get(),
            "goto_found": self.combo_goto_found.get(),
            "timeout_seconds": int(self.entry_wait.get() or 0),
            "goto_notfound": self.combo_goto_notfound.get(),
            "search_area_mode": area_mode,
            "custom_region": self.search_region
        }
        self.callback(payload)
        self.destroy()


# ==========================================================
# MAIN APPLICATION PLATFORM
# ==========================================================
class ProfessionalMacroStudio(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MacroBot Pro Studio")
        self.geometry("1050x650")
        self.configure(fg_color="#1E1E2E")

        self.macro_steps = []
        self.is_recording = False
        self.is_running = False
        self.last_action_time = time.time()
        
        self.mouse_listener = None
        self.key_listener = None
        self.hotkey_listener = None

        self.setup_ui()
        self.init_global_hotkeys()

    def setup_ui(self):
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.toolbar = ctk.CTkFrame(self, fg_color="#252538", height=90, corner_radius=0, border_color="#313244", border_width=1)
        self.toolbar.grid(row=0, column=0, sticky="ew")
        self.toolbar.grid_propagate(False)

        self.build_toolbar_button("▶ Play\n(F9)", "#A6E3A1", self.start_macro_playback, 10)
        self.btn_record = self.build_toolbar_button("🔴 Record\n(F8)", "#FAB387", self.toggle_recording, 85)
        self.build_toolbar_button("⏹ Stop\n(ESC)", "#F38BA8", self.stop_operations, 160)
        
        self.build_divider(235)

        self.build_toolbar_button("鼠标\nMouse", "#CDD6F4", self.add_manual_click, 250, mini=True)
        self.build_toolbar_button("键盘\nText/Key", "#CDD6F4", self.add_manual_type, 315, mini=True)
        self.build_toolbar_button("等待\nWait", "#CDD6F4", self.add_manual_wait, 380, mini=True)
        self.build_toolbar_button("图像\nImage/OCR", "#CDD6F4", self.open_image_config_modal, 445, mini=True)

        self.build_divider(520)

        self.build_toolbar_button("删除\nDelete", "#F38BA8", self.delete_selected_row, 540, mini=True)
        self.build_toolbar_button("清空\nClear All", "#585B70", self.clear_all_steps, 605, mini=True)
        self.build_toolbar_button("保存\nSave", "#7AA2F7", self.save_workflow, 670, mini=True)
        self.build_toolbar_button("读取\nLoad", "#7AA2F7", self.load_workflow, 735, mini=True)

        self.loop_count_var = tk.StringVar(value="1")
        lbl_loop = ctk.CTkLabel(self.toolbar, text="Loop:", font=ctk.CTkFont(size=10), text_color="#CDD6F4")
        lbl_loop.place(x=805, y=43)
        vcmd = (self.register(self.validate_loop_count), '%P')
        self.loop_count_entry = ctk.CTkEntry(self.toolbar, width=60, height=28, fg_color="#13131F", border_color="#313244", textvariable=self.loop_count_var, justify="center", validate="key", validatecommand=vcmd)
        self.loop_count_entry.place(x=840, y=40)
        self.loop_count_entry.bind("<FocusOut>", lambda event: self.loop_count_var.set(str(self.get_play_loop_count())))

        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=15)
        
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#13131F", foreground="#CDD6F4", fieldbackground="#13131F", rowheight=28, font=("Segoe UI", 11), borderwidth=0)
        style.configure("Treeview.Heading", background="#252538", foreground="white", font=("Segoe UI", 11, "bold"), borderwidth=1)
        style.map("Treeview", background=[('selected', '#313244')], foreground=[('selected', '#F5E0DC')])

        columns = ("action", "value", "label", "comment")
        self.table = ttk.Treeview(self.grid_frame, columns=columns, show="headings", selectmode="browse")
        
        self.table.heading("action", text="Action")
        self.table.heading("value", text="Value")
        self.table.heading("label", text="Label")
        self.table.heading("comment", text="Comment")

        self.table.column("action", width=140, anchor="w")
        self.table.column("value", width=260, anchor="w")
        self.table.column("label", width=180, anchor="w")
        self.table.column("comment", width=430, anchor="w")

        scrollbar = ttk.Scrollbar(self.grid_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.table.bind("<Double-1>", self.on_row_double_click)

    def build_toolbar_button(self, text, color, command, x_pos, mini=False):
        w, h = (60, 56) if mini else (70, 60)
        txt_clr = "#11111B" if color not in ["#CDD6F4", "#585B70"] else "white"
        btn = ctk.CTkButton(self.toolbar, text=text, fg_color=color, text_color=txt_clr, hover_color=color, width=w, height=h, corner_radius=6, font=ctk.CTkFont(size=10 if mini else 11, weight="bold"), command=command)
        btn.place(x=x_pos, y=15)
        return btn

    def build_divider(self, x_pos):
        div = ctk.CTkFrame(self.toolbar, width=2, height=50, fg_color="#313244")
        div.place(x=x_pos, y=20)

    def open_image_config_modal(self, initial_payload=None, edit_index=None):
        ImageSearchConfigModal(self, lambda payload: self.insert_image_action_callback(payload, edit_index), initial_payload=initial_payload)

    def insert_image_action_callback(self, payload, edit_index=None):
        short_filename = payload["path"].split("/")[-1] if "/" in payload["path"] else payload["path"].split("\\")[-1]
        action_title = "Image Search"
        
        if payload.get("custom_region"):
            r = payload["custom_region"]
            value_desc = f"Area: [{r[0]},{r[1]} {r[2]}x{r[3]}] ({short_filename})"
        else:
            value_desc = f"Area: {payload['search_area_mode']} ({short_filename})"
            
        label_desc = f"If Found -> {payload['action_type']}"
        comment_desc = f"Wait {payload['timeout_seconds']}s, Else -> {payload['goto_notfound']}"

        if edit_index is not None and 0 <= edit_index < len(self.macro_steps):
            self.macro_steps[edit_index] = {"type": action_title, "value": value_desc, "img_payload": payload}
            item = self.table.get_children()[edit_index]
            self.table.item(item, values=(action_title, value_desc, label_desc, comment_desc))
        else:
            self.insert_step_row(action_title, value_desc, label_desc, comment_desc, extra_data={"img_payload": payload})

    def init_global_hotkeys(self):
        def routing(key):
            try:
                if key == keyboard.Key.f8: self.after(0, self.toggle_recording)
                elif key == keyboard.Key.f9: self.after(0, self.start_macro_playback)
                elif key == keyboard.Key.esc: self.after(0, self.stop_operations)
            except Exception: pass
        self.hotkey_listener = keyboard.Listener(on_press=routing)
        self.hotkey_listener.start()

    def on_row_double_click(self, event):
        item = self.table.identify_row(event.y)
        if not item:
            return
        index = self.table.index(item)
        if index < 0 or index >= len(self.macro_steps):
            return
        step = self.macro_steps[index]

        if step.get("type") == "Image Search":
            payload = step.get("img_payload", step)
            self.open_image_config_modal(initial_payload=payload, edit_index=index)
            return

        if step.get("type") == "Wait":
            self.edit_wait_step(index)
            return

        if step.get("type") == "Mouse Click":
            self.edit_mouse_click_step(index)
            return

        if step.get("type") == "Type Text":
            self.edit_type_text_step(index)
            return

    def edit_wait_step(self, index):
        step = self.macro_steps[index]
        current = step.get("value", "0 ms")
        try:
            current_ms = int(current.split()[0])
        except Exception:
            current_ms = 100
        ms = simpledialog.askinteger("Edit Wait", "Duration (ms):", initialvalue=current_ms, parent=self)
        if ms is not None:
            self.macro_steps[index]["value"] = f"{ms} ms"
            item = self.table.get_children()[index]
            self.table.item(item, values=("Wait", f"{ms} ms", "", f"Pause execution flow for {ms}ms"))

    def edit_mouse_click_step(self, index):
        step = self.macro_steps[index]
        value = step.get("value", "X: 0, Y: 0")
        x = 0
        y = 0
        try:
            parts = value.split(",")
            x = int(parts[0].split(":")[1].strip())
            y = int(parts[1].split(":")[1].strip())
        except Exception:
            pass
        nx = simpledialog.askinteger("Edit Mouse Click", "X target pixel:", initialvalue=x, parent=self)
        if nx is None:
            return
        ny = simpledialog.askinteger("Edit Mouse Click", "Y target pixel:", initialvalue=y, parent=self)
        if ny is None:
            return
        self.macro_steps[index]["value"] = f"X: {nx}, Y: {ny}"
        item = self.table.get_children()[index]
        self.table.item(item, values=("Mouse Click", f"X: {nx}, Y: {ny}", "Centered", "Click left mouse button"))

    def edit_type_text_step(self, index):
        step = self.macro_steps[index]
        current = step.get("value", "")
        text = simpledialog.askstring("Edit Text", "Enter new text:", initialvalue=current, parent=self)
        if text is not None:
            self.macro_steps[index]["value"] = text
            item = self.table.get_children()[index]
            self.table.item(item, values=("Type Text", text, "", "Inject text entry keystroke"))

    def toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            self.clear_all_steps()
            self.last_action_time = time.time()
            self.withdraw() 
            self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
            self.key_listener = keyboard.Listener(on_press=self.on_key_press)
            self.mouse_listener.start()
            self.key_listener.start()
        else:
            self.stop_operations()

    def on_mouse_click(self, x, y, button, pressed):
        if pressed and self.is_recording:
            now = time.time()
            delay = int((now - self.last_action_time) * 1000)
            if delay > 40:
                self.insert_step_row("Wait", f"{delay} ms", "", f"Pause execution flow for {delay}ms")
                self.insert_step_row("Mouse Click", f"X: {x}, Y: {y}", "Centered", "Click left mouse button")
                self.last_action_time = now

    def on_key_press(self, key):
        if not self.is_recording or key in [keyboard.Key.f8, keyboard.Key.f9, keyboard.Key.esc]: return
        now = time.time()
        delay = int((now - self.last_action_time) * 1000)
        
        if key == keyboard.Key.space: char = " "
        elif hasattr(key, 'char') and key.char is not None: char = key.char
        else: char = f"[{str(key).replace('Key.', '')}]"

        if delay > 20:
            self.insert_step_row("Wait", f"{delay} ms", "", f"Pause execution flow for {delay}ms")
            self.insert_step_row("Type Text", char, "", "Inject text entry keystroke")
            self.last_action_time = now

    def stop_operations(self):
        self.is_recording = False
        self.is_running = False
        if self.mouse_listener: self.mouse_listener.stop()
        if self.key_listener: self.key_listener.stop()
        self.deiconify()

    def start_macro_playback(self):
        if not self.macro_steps: return
        self.is_running = True
        self.withdraw()
        self.play_loop_count = self.get_play_loop_count()
        threading.Thread(target=self.run_playback_loop, daemon=True).start()

    def get_play_loop_count(self):
        try:
            count = int(self.loop_count_var.get())
        except Exception:
            count = 1
        return max(1, count)

    def validate_loop_count(self, value):
        if value == "":
            return True
        return value.isdigit()

    def save_workflow(self):
        if not self.macro_steps:
            messagebox.showwarning("Save Workflow", "There is no workflow to save.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Macro Files", "*.json"), ("All Files", "*")],
            title="Save Workflow"
        )
        if not file_path:
            return

        payload = {
            "loop_count": self.get_play_loop_count(),
            "steps": self.macro_steps
        }

        try:
            with open(file_path, "w", encoding="utf-8") as fp:
                json.dump(payload, fp, indent=2, ensure_ascii=False)
            messagebox.showinfo("Save Workflow", f"Workflow saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Save Workflow", f"Unable to save workflow:\n{e}")

    def load_workflow(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Macro Files", "*.json"), ("All Files", "*")],
            title="Load Workflow"
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception as e:
            messagebox.showerror("Load Workflow", f"Unable to read file:\n{e}")
            return

        if not isinstance(data, dict) or "steps" not in data:
            messagebox.showerror("Load Workflow", "This file does not contain a valid workflow.")
            return

        self.load_workflow_data(data)

    def load_workflow_data(self, data):
        self.clear_all_steps()
        self.macro_steps = []

        self.loop_count_var.set(str(max(1, int(data.get("loop_count", 1)))))

        for step in data.get("steps", []):
            if not isinstance(step, dict) or "type" not in step or "value" not in step:
                continue

            action_type = step["type"]
            value = step["value"]
            label = ""
            comment = ""

            if action_type == "Mouse Click":
                label = "Centered"
                comment = "Click left mouse button"
            elif action_type == "Type Text":
                label = ""
                comment = "Inject text entry keystroke"
            elif action_type == "Wait":
                comment = f"Pause execution flow for {value}"
            elif action_type == "Image Search":
                payload = step.get("img_payload", {})
                short_filename = payload.get("path", "Image")
                short_filename = short_filename.split("/")[-1].split("\\")[-1]
                if payload.get("custom_region"):
                    region = payload["custom_region"]
                    value = f"Area: [{region[0]},{region[1]} {region[2]}x{region[3]}] ({short_filename})"
                else:
                    value = f"Area: {payload.get('search_area_mode', 'Entire desktop')} ({short_filename})"
                label = f"If Found -> {payload.get('action_type', 'Left Click')}"
                comment = f"Wait {payload.get('timeout_seconds', 0)}s, Else -> {payload.get('goto_notfound', 'End')}"

            self.insert_step_row(action_type, value, label, comment, extra_data={k: v for k, v in step.items() if k not in {"type", "value"}})

        self.after(0, lambda: self.loop_count_var.set(str(self.get_play_loop_count())))

    def run_playback_loop(self):
        # Prevent OS scaling issues on Windows by declaring DPI awareness
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2) # Per-Monitor DPI Aware
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware() # Fallback for older systems
            except Exception:
                pass # Non-Windows environment

        time.sleep(1.0)
        pyautogui.MINIMUM_DURATION = 0.05 # Add safe internal movement padding
        pyautogui.FAILSAFE = True          # Slam mouse into top-left corner to abort macro

        stop_all = False
        for cycle in range(self.play_loop_count):
            if not self.is_running or stop_all:
                break

            for idx, step in enumerate(self.macro_steps):
                if not self.is_running or stop_all:
                    break
                
                stype = step["type"]
                val = step["value"]

                try:
                    if stype == "Wait":
                        val_str = str(val)
                        time.sleep(int(val_str.split()[0]) / 1000.0)
                        
                    elif stype == "Mouse Click":
                        val_str = str(val)
                        parts = val_str.split(", ")
                        x = int(parts[0].split(": ")[1])
                        y = int(parts[1].split(": ")[1])
                        
                        # Hardened Playback Routine: Move -> Pause -> Click with duration
                        pyautogui.moveTo(x, y, duration=0.15)
                        time.sleep(0.05)
                        pyautogui.click(x, y, duration=0.10)
                        time.sleep(0.05)
                        
                    elif stype == "Type Text":
                        val_str = str(val)
                        if val_str.startswith("[") and val_str.endswith("]"): 
                            pyautogui.press(val_str[1:-1].lower())
                        else: 
                            pyautogui.write(val_str, interval=0.02)
                            
                    elif stype == "Image Search":
                        if "img_payload" in step:
                            success = self.execute_live_image_search(step["img_payload"])
                            if not success and step["img_payload"].get("goto_notfound") == "End":
                                stop_all = True
                                break
                except Exception as e:
                    print(f"Error processing step {idx} [{stype}]: {e}")
                    continue

        self.after(0, self.deiconify)
        self.is_running = False

    def execute_live_image_search(self, config):
        start_time = time.time()
        timeout = config["timeout_seconds"]
        tolerance = config["tolerance"]
        region = config["custom_region"]

        while (time.time() - start_time) < timeout:
            if not self.is_running: 
                return False
            
            try:
                if region:
                    screen = pyautogui.screenshot(region=region)
                    offset_x, offset_y = region[0], region[1]
                else:
                    screen = pyautogui.screenshot()
                    offset_x, offset_y = 0, 0
                    
                screen_cv = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)
                template = cv2.imread(config["path"])
                
                if template is None:
                    return False
                    
                res = cv2.matchTemplate(screen_cv, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)

                if max_val >= (1.0 - tolerance):
                    if config["mouse_action_enabled"]:
                        h, w, _ = template.shape
                        cx = offset_x + max_loc[0] + int(w / 2)
                        cy = offset_y + max_loc[1] + int(h / 2)
                        
                        # Apply identical hardened movement and clicking safety to image hits
                        pyautogui.moveTo(cx, cy, duration=0.15)
                        time.sleep(0.05)
                        
                        if config["action_type"] == "Left Click": 
                            pyautogui.click(cx, cy, duration=0.10)
                        elif config["action_type"] == "Right Click": 
                            pyautogui.rightClick(cx, cy, duration=0.10)
                        elif config["action_type"] == "Hover Only": 
                            pass # Already moved there
                            
                        time.sleep(0.05)
                    return True
            except Exception as e:
                print(f"Error encountered during screen monitoring loop: {e}")
                
            time.sleep(0.25) # Standardized cycle tick
        return False

    def insert_step_row(self, action, value, label, comment, extra_data=None):
        step_entry = {"type": action, "value": value}
        if extra_data: step_entry.update(extra_data)
        self.macro_steps.append(step_entry)
        self.after(0, lambda: self.table.insert("", "end", values=(action, value, label, comment)))

    def delete_selected_row(self):
        try:
            selected_item = self.table.selection()[0]
            idx = self.table.index(selected_item)
            self.table.delete(selected_item)
            self.macro_steps.pop(idx)
        except IndexError:
            messagebox.showwarning("Selection", "Please select a row first!")

    def clear_all_steps(self):
        self.macro_steps.clear()
        for row in self.table.get_children():
            self.table.delete(row)

    def add_manual_click(self):
        x = simpledialog.askinteger("Input", "X target pixel:")
        y = simpledialog.askinteger("Input", "Y target pixel:")
        if x is not None and y is not None:
            self.insert_step_row("Mouse Click", f"X: {x}, Y: {y}", "Centered", "Click left mouse button")

    def add_manual_type(self):
        text = simpledialog.askstring("Input", "Enter text pattern:")
        if text:
            self.insert_step_row("Type Text", text, "", "Inject text entry keystroke")

    def add_manual_wait(self):
        ms = simpledialog.askinteger("Input", "Enter duration (ms):")
        if ms:
            self.insert_step_row("Wait", f"{ms} ms", "", f"Pause execution flow for {ms}ms")

if __name__ == "__main__":
    app = ProfessionalMacroStudio()
    app.mainloop()