__version__ = "1.6.0"

import socket
import json
import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

# --- CONFIGURATION ---
#VIDEOHUB_IP = "10.110.1.150"  # Live hardware router IP address
#VIDEOHUB_PORT = 9990          # Default Blackmagic Videohub Ethernet protocol port
JSON_FILE = "BlackMagic_Videohub_Map.json"  # Assigned preset file
MOCK_LABELS_FILE = "Mock_Hardware_Labels.json" # Offline simulation file
DEFAULT_OFFLINE_SIZE = 40     # Pads out ports to a 40x40 matrix when offline

class SalvoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Videohub Matrix Controller")
        self.root.geometry("540x740")
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.configure_carbon_styles()
        self.root.configure(bg="#f4f4f4")
        
        # Load presets data first so we can parse out network configs if they exist
        self.presets = self.load_presets_from_file()
        
        # Pull saved connection states from JSON profile, or use hardcoded fallbacks
        self.videohub_ip = self.presets.get("__network_config__", {}).get("ip", "10.110.1.150")
        self.videohub_port = self.presets.get("__network_config__", {}).get("port", 9990)
        
        # Clean the system key out of active salvo maps so it doesn't render as a preset button
        if "__network_config__" in self.presets:
            del self.presets["__network_config__"]
        
        self.input_labels = {}
        self.output_labels = {}
        
        print(f"[LIVE] Initializing Carbon UI Workspace (v1.8.0)...")
        self.fetch_hardware_labels()

        # Header Title Area
        header_frame = tk.Frame(root, bg="#ffffff", bd=0, highlightthickness=1, highlightbackground="#e0e0e0")
        header_frame.pack(fill=tk.X, side=tk.TOP)
        
        title_label = tk.Label(
            header_frame, text="Videohub Matrix Presets", 
            font=("Helvetica Neue", 16), fg="#161616", bg="#ffffff", padx=24, pady=16, anchor="w"
        )
        title_label.pack(fill=tk.X)

        # Presets Workspace
        self.container = tk.Frame(root, bg="#f4f4f4")
        self.container.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)
        
        self.canvas = tk.Canvas(self.container, borderwidth=0, highlightthickness=0, bg="#f4f4f4")
        self.scrollbar = ttk.Scrollbar(self.container, orient="vertical", command=self.canvas.yview)
        self.button_frame = tk.Frame(self.canvas, bg="#f4f4f4")
        
        self.button_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.button_frame, anchor="nw", width=460)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Bottom Functional Utility Dock (Grid aligned)
        utils_frame = tk.Frame(root, bg="#ffffff", bd=0, highlightthickness=1, highlightbackground="#e0e0e0")
        utils_frame.pack(side=tk.BOTTOM, fill=tk.X)

        grid_container = tk.Frame(utils_frame, bg="#ffffff")
        grid_container.pack(fill=tk.X, padx=24, pady=20)
        grid_container.columnconfigure(0, weight=1)
        grid_container.columnconfigure(1, weight=1)

        new_preset_btn = ttk.Button(grid_container, text="Create Preset", style="CarbonSecondary.TButton", command=self.open_preset_editor)
        new_preset_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 10))

        capture_btn = ttk.Button(grid_container, text="Capture Matrix", style="CarbonSecondary.TButton", command=self.capture_live_matrix)
        capture_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 10))

        manage_labels_btn = ttk.Button(grid_container, text="Edit Port Labels", style="CarbonSecondary.TButton", command=self.open_labels_editor)
        manage_labels_btn.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(0, 10))

        test_conn_btn = ttk.Button(grid_container, text="Sync Hardware", style="CarbonSecondary.TButton", command=self.test_connection)
        test_conn_btn.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(0, 10))
        
        network_settings_btn = ttk.Button(grid_container, text="⚙️ Network Configuration", style="CarbonSecondary.TButton", command=self.open_network_settings)
        network_settings_btn.grid(row=2, column=0, columnspan=2, sticky="ew", padx=0, pady=0)

        # Status Footer Item
        self.status_var = tk.StringVar()
        self.update_status_footer()
        status_label = tk.Label(
            root, textvariable=self.status_var, bd=0, anchor=tk.W, 
            font=("Helvetica Neue", 11), bg="#e0e0e0", fg="#525252", padx=24, pady=6
        )
        status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.render_preset_buttons()

    def update_status_footer(self, message=None):
        """Helper to keep runtime labels sync'd with chosen properties."""
        if message:
            self.status_var.set(message)
        else:
            self.status_var.set(f"Hardware Target: {self.videohub_ip}:{self.videohub_port}")

    def configure_carbon_styles(self):
        """Builds modern flat structure layout blocks adhering to Carbon layout system."""
        # Carbon Secondary Action Button Layout & Focus Ring strip-out
        self.style.configure("CarbonSecondary.TButton", font=("Helvetica Neue", 11), padding=(16, 10), background="#393939", foreground="#ffffff", borderwidth=0)
        self.style.map("CarbonSecondary.TButton", 
            background=[("active", "#4d4d4d")],
            focuscolor=[("focus", "#393939")], # Removes unstyled dotted focus borders
            highlightthickness=[("focus", 0)]
        )

        # Carbon List Button Item
        self.style.configure("CarbonList.TButton", font=("Helvetica Neue", 12), padding=(16, 12), background="#ffffff", foreground="#161616", borderwidth=1, bordercolor="#e0e0e0")
        self.style.map("CarbonList.TButton", background=[("active", "#e5e5e5")], focuscolor=[("focus", "#ffffff")])

        # Clean Notebook Tab Deck
        self.style.configure("TNotebook", background="#ffffff", borderwidth=0)
        self.style.configure("TNotebook.Tab", font=("Helvetica Neue", 11), padding=(16, 6), background="#e0e0e0", foreground="#525252", borderwidth=0)
        self.style.map("TNotebook.Tab", 
            background=[("selected", "#ffffff")], 
            foreground=[("selected", "#161616")],
            padding=[("selected", (16, 12))]
        )

    def fetch_hardware_labels(self):
        response = ""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect((self.videohub_IP, self.videohub_PORT))
                while True:
                    chunk = s.recv(8192).decode('utf-8', errors='ignore')
                    if not chunk: break
                    response += chunk
                    if "VIDEO OUTPUT ROUTING:" in response:
                        break
                        
            if "INPUT LABELS:\n" in response:
                self.input_labels.clear()
                input_block = response.split("INPUT LABELS:\n")[1].split("\n\n")[0]
                for line in input_block.strip().split("\n"):
                    parts = line.split(" ", 1)
                    if len(parts) == 2: self.input_labels[parts[0].strip()] = parts[1].strip()

            if "OUTPUT LABELS:\n" in response:
                self.output_labels.clear()
                output_block = response.split("OUTPUT LABELS:\n")[1].split("\n\n")[0]
                for line in output_block.strip().split("\n"):
                    parts = line.split(" ", 1)
                    if len(parts) == 2: self.output_labels[parts[0].strip()] = parts[1].strip()
            return
        except Exception:
            pass

        file_inputs = {}
        file_outputs = {}
        if os.path.exists(MOCK_LABELS_FILE):
            try:
                with open(MOCK_LABELS_FILE, "r") as f:
                    data = json.load(f)
                    file_inputs = data.get("INPUT_LABELS", {})
                    file_outputs = data.get("OUTPUT_LABELS", {})
            except Exception:
                pass

        self.input_labels = {str(i): file_inputs.get(str(i), f"Input {i+1}") for i in range(DEFAULT_OFFLINE_SIZE)}
        self.output_labels = {str(o): file_outputs.get(str(o), f"Output {o+1}") for o in range(DEFAULT_OFFLINE_SIZE)}

    def render_preset_buttons(self):
        for widget in self.button_frame.winfo_children():
            widget.destroy()

        if not self.presets:
            lbl = tk.Label(self.button_frame, text="No saved presets found.", fg="#6f6f6f", bg="#f4f4f4", font=("Helvetica Neue", 12))
            lbl.pack(pady=40, anchor="w", padx=10)
            return

        for name, mapping in self.presets.items():
            row = tk.Frame(self.button_frame, bg="#f4f4f4", pady=3)
            row.pack(fill=tk.X)
            
            # Left side line border representation matching layout panels
            border_indicator = tk.Frame(row, width=4, bg="#0f62fe") # Carbon Blue primary highlight accent bar
            border_indicator.pack(side=tk.LEFT, fill=tk.Y)
            
            btn = ttk.Button(row, text=f"  {name}", style="CarbonList.TButton", command=lambda p=name, m=mapping: self.deploy_salvo(p, m))
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            edit_btn = ttk.Button(row, text="Edit", width=6, style="CarbonSecondary.TButton", command=lambda p=name, m=mapping: self.open_preset_editor(p, m))
            edit_btn.pack(side=tk.RIGHT, padx=(4, 0))

    def open_labels_editor(self):
        label_editor = tk.Toplevel(self.root)
        label_editor.title("Edit Hardware Port Labels")
        label_editor.geometry("500x600")
        label_editor.configure(bg="#ffffff")
        label_editor.grab_set()

        notebook = ttk.Notebook(label_editor)
        notebook.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        tabs = {}
        for tab_name, labels_dict, fallback_prefix in [("Inputs", self.input_labels, "Input"), ("Outputs", self.output_labels, "Output")]:
            frame = tk.Frame(notebook, bg="#ffffff")
            notebook.add(frame, text=tab_name)
            
            canvas = tk.Canvas(frame, borderwidth=0, highlightthickness=0, bg="#ffffff")
            scroll = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
            container = tk.Frame(canvas, bg="#ffffff")
            
            container.bind("<Configure>", lambda e, c=canvas: c.configure(scrollregion=c.bbox("all")))
            canvas.create_window((0, 0), window=container, anchor="nw", width=440)
            canvas.configure(yscrollcommand=scroll.set)
            canvas.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")
            tabs[tab_name] = (container, labels_dict, fallback_prefix)

        entries = {"Inputs": {}, "Outputs": {}}
        for tab_name, (container, labels_dict, prefix) in tabs.items():
            for idx in sorted(labels_dict.keys(), key=int):
                row = tk.Frame(container, bg="#ffffff", pady=6)
                row.pack(fill=tk.X, padx=10)
                
                tk.Label(row, text=f"{prefix} {int(idx)+1:02d}", font=("Helvetica Neue", 11), fg="#525252", bg="#ffffff", width=10, anchor="w").pack(side=tk.LEFT)
                
                ent = tk.Entry(row, font=("Helvetica Neue", 11), bg="#f4f4f4", fg="#161616", bd=0, highlightthickness=1, highlightbackground="#8d8d8d")
                ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8), ipady=4)
                ent.insert(0, labels_dict[idx])
                entries[tab_name][idx] = ent
                
                clr_btn = tk.Label(row, text="Clear", fg="#da1e28", bg="#ffffff", cursor="hand2", font=("Helvetica Neue", 10))
                clr_btn.pack(side=tk.RIGHT, padx=4)
                clr_btn.bind("<Button-1>", lambda e, entry=ent, p=prefix, i=idx: [entry.delete(0, tk.END), entry.insert(0, f"{p} {int(i)+1}")])

        def commit_label_changes():
            new_inputs = {idx: ent.get().strip() for idx, ent in entries["Inputs"].items() if ent.get().strip()}
            new_outputs = {idx: ent.get().strip() for idx, ent in entries["Outputs"].items() if ent.get().strip()}

            in_cmd = "INPUT LABELS:\n" + "".join([f"{idx} {name}\n" for idx, name in new_inputs.items()]) + "\n"
            out_cmd = "OUTPUT LABELS:\n" + "".join([f"{idx} {name}\n" for idx, name in new_outputs.items()]) + "\n"

            online_success = False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2.0)
                    s.connect((self.videohub_IP, self.videohub_PORT))
                    s.recv(4096)
                    s.sendall(in_cmd.encode('utf-8'))
                    s.sendall(out_cmd.encode('utf-8'))
                online_success = True
            except Exception:
                pass

            try:
                with open(MOCK_LABELS_FILE, "w") as f:
                    json.dump({"INPUT_LABELS": new_inputs, "OUTPUT_LABELS": new_outputs}, f, indent=4)
            except Exception as file_err:
                messagebox.showerror("Error", f"Failed to save simulation edits: {file_err}")

            self.input_labels = new_inputs
            self.output_labels = new_outputs
            label_editor.destroy()
            
            if online_success:
                messagebox.showinfo("Success", "Labels successfully updated on the live Videohub router!")
                self.status_var.set("Labels Pushed Online Successfully")
            else:
                messagebox.showinfo("Offline Saved", "Router is offline. Modified labels saved to local mock profile file.")
                self.status_var.set("Labels Saved to Local Mock File")

        actions_frame = tk.Frame(label_editor, bg="#f4f4f4", pady=16, bd=0, highlightthickness=1, highlightbackground="#e0e0e0")
        actions_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Switched to explicit tk.Button to prevent theme-collapsing bugs
        save_btn = tk.Button(
            actions_frame, text="Commit Label Edits", font=("Helvetica Neue", 11),
            bg="#161616", fg="#ffffff", activebackground="#393939", activeforeground="#ffffff",
            relief="flat", bd=0, padx=20, pady=10, cursor="hand2"
        )
        save_btn.pack(side=tk.RIGHT, padx=24)
        save_btn.bind("<Button-1>", lambda e: commit_label_changes())

    def open_preset_editor(self, preset_name="", mapping=None):
        editor = tk.Toplevel(self.root)
        editor.title("Modify Preset" if preset_name else "Create New Preset")
        editor.geometry("500x600") # Expanded frame depth safely
        editor.configure(bg="#ffffff")
        editor.grab_set()

        src_choices = [f"{self.input_labels[idx]} ({int(idx) + 1})" for idx in sorted(self.input_labels.keys(), key=int)]
        src_map_lookup = {disp: idx for idx in self.input_labels for disp in [f"{self.input_labels[idx]} ({int(idx) + 1})"]}

        dest_choices = [f"{self.output_labels[idx]} ({int(idx) + 1})" for idx in sorted(self.output_labels.keys(), key=int)]
        dest_map_lookup = {disp: idx for idx in self.output_labels for disp in [f"{self.output_labels[idx]} ({int(idx) + 1})"]}

        tk.Label(editor, text="Preset Name", font=("Helvetica Neue", 11), fg="#525252", bg="#ffffff").pack(anchor=tk.W, padx=24, pady=(20, 4))
        name_entry = tk.Entry(editor, font=("Helvetica Neue", 12), bg="#f4f4f4", fg="#161616", bd=0, highlightthickness=1, highlightbackground="#8d8d8d")
        name_entry.pack(fill=tk.X, padx=24, pady=(0, 15), ipady=5)
        if preset_name:
            name_entry.insert(0, preset_name)

        tk.Label(editor, text="Cross-point Mappings", font=("Helvetica Neue", 11), fg="#525252", bg="#ffffff").pack(anchor=tk.W, padx=24, pady=(5, 4))
        
        table_frame = tk.Frame(editor, bg="#ffffff")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=5)
        
        canvas = tk.Canvas(table_frame, borderwidth=0, highlightthickness=0, bg="#ffffff")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=canvas.yview)
        rows_container = tk.Frame(canvas, bg="#ffffff")
        
        rows_container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=rows_container, anchor="nw", width=420)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        mapping_rows = []

        def add_mapping_row(initial_s_0b=None, initial_d_0b=None):
            r = tk.Frame(rows_container, bg="#ffffff", pady=6)
            r.pack(fill=tk.X)
            
            tk.Label(r, text="Src:", font=("Helvetica Neue", 10), bg="#ffffff", fg="#525252").pack(side=tk.LEFT, padx=2)
            s_combo = ttk.Combobox(r, values=src_choices, width=16, state="readonly")
            s_combo.pack(side=tk.LEFT, padx=2)
            
            tk.Label(r, text="➔ Dest:", font=("Helvetica Neue", 10), bg="#ffffff", fg="#525252").pack(side=tk.LEFT, padx=2)
            d_combo = ttk.Combobox(r, values=dest_choices, width=16, state="readonly")
            d_combo.pack(side=tk.LEFT, padx=2)
            
            if initial_s_0b in self.input_labels:
                s_combo.set(f"{self.input_labels[initial_s_0b]} ({int(initial_s_0b) + 1})")
            elif src_choices:
                s_combo.set(src_choices[0])

            if initial_d_0b in self.output_labels:
                d_combo.set(f"{self.output_labels[initial_d_0b]} ({int(initial_d_0b) + 1})")
            elif dest_choices:
                d_combo.set(dest_choices[0])
            
            del_lbl = tk.Label(r, text="Remove", fg="#da1e28", bg="#ffffff", cursor="hand2", font=("Helvetica Neue", 10))
            del_lbl.pack(side=tk.RIGHT, padx=6)
            del_lbl.bind("<Button-1>", lambda e: [r.destroy(), mapping_rows.remove((s_combo, d_combo))])
            
            mapping_rows.append((s_combo, d_combo))

        if mapping:
            for d_0b, s_0b in mapping.items():
                add_mapping_row(str(s_0b), str(d_0b))
        else:
            add_mapping_row()

        # Added explicit height definitions to prevent squishing
        add_row_btn = tk.Button(
            editor, text="➕ Add Assignment Row", font=("Helvetica Neue", 10, "bold"),
            bg="#ffffff", fg="#161616", activebackground="#e5e5e5", activeforeground="#161616",
            relief="flat", bd=0, highlightthickness=1, highlightbackground="#8d8d8d",
            padx=14, pady=8, cursor="hand2"
        )
        add_row_btn.pack(pady=15)
        add_row_btn.bind("<Button-1>", lambda e: add_mapping_row())

        def save_edited_data():
            raw_name = name_entry.get().strip()
            if not raw_name:
                messagebox.showerror("Error", "Preset Name cannot be blank.")
                return
            
            new_map = {}
            for s_combo, d_combo in mapping_rows:
                s_sel = s_combo.get()
                d_sel = d_combo.get()
                if s_sel and d_sel:
                    s_0b = src_map_lookup.get(s_sel)
                    d_0b = dest_map_lookup.get(d_sel)
                    if s_0b is not None and d_0b is not None:
                        new_map[d_0b] = s_0b

            if preset_name and preset_name != raw_name and preset_name in self.presets:
                del self.presets[preset_name]
                
            self.presets[raw_name] = new_map
            self.save_presets_to_file()
            self.render_preset_buttons()
            editor.destroy()
            self.status_var.set(f"Saved layout: '{raw_name}'")

        actions_frame = tk.Frame(editor, bg="#f4f4f4", pady=16, bd=0, highlightthickness=1, highlightbackground="#e0e0e0")
        actions_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        save_btn = tk.Button(
            actions_frame, text="Save Changes", font=("Helvetica Neue", 11, "bold"),
            bg="#161616", fg="#ffffff", activebackground="#393939", activeforeground="#ffffff",
            relief="flat", bd=0, padx=24, pady=10, cursor="hand2"
        )
        save_btn.pack(side=tk.RIGHT, padx=24)
        save_btn.bind("<Button-1>", lambda e: save_edited_data())
        
        if preset_name:
            def delete_preset():
                if messagebox.askyesno("Confirm Delete", f"Are you sure you want to completely remove '{preset_name}'?"):
                    del self.presets[preset_name]
                    self.save_presets_to_file()
                    self.render_preset_buttons()
                    editor.destroy()
                    self.status_var.set(f"Deleted preset: '{preset_name}'")
                    
            del_btn = tk.Button(
                actions_frame, text="Delete Preset", font=("Helvetica Neue", 11),
                bg="#da1e28", fg="#ffffff", activebackground="#b81922", activeforeground="#ffffff",
                relief="flat", bd=0, padx=20, pady=10, cursor="hand2"
            )
            del_btn.pack(side=tk.LEFT, padx=24)
            del_btn.bind("<Button-1>", lambda e: delete_preset())

    def open_network_settings(self):
        settings_dialog = tk.Toplevel(self.root)
        settings_dialog.title("Network Configuration")
        settings_dialog.geometry("400x300")
        settings_dialog.configure(bg="#ffffff")
        settings_dialog.grab_set()

        tk.Label(settings_dialog, text="Router IP Address", font=("Helvetica Neue", 11), fg="#525252", bg="#ffffff").pack(anchor=tk.W, padx=24, pady=(20, 4))
        ip_entry = tk.Entry(settings_dialog, font=("Helvetica Neue", 12), bg="#f4f4f4", fg="#161616", bd=0, highlightthickness=1, highlightbackground="#8d8d8d")
        ip_entry.pack(fill=tk.X, padx=24, pady=(0, 15), ipady=5)
        ip_entry.insert(0, self.videohub_ip)

        tk.Label(settings_dialog, text="Control Port", font=("Helvetica Neue", 11), fg="#525252", bg="#ffffff").pack(anchor=tk.W, padx=24, pady=(0, 4))
        port_entry = tk.Entry(settings_dialog, font=("Helvetica Neue", 12), bg="#f4f4f4", fg="#161616", bd=0, highlightthickness=1, highlightbackground="#8d8d8d")
        port_entry.pack(fill=tk.X, padx=24, pady=(0, 20), ipady=5)
        port_entry.insert(0, str(self.videohub_port))

        def save_network_config():
            ip_str = ip_entry.get().strip()
            port_str = port_entry.get().strip()

            if not ip_str:
                messagebox.showerror("Validation Error", "IP Address cannot be empty.")
                return
            try:
                port_val = int(port_str)
                if not (1 <= port_val <= 65535):
                    raise ValueError
            except ValueError:
                messagebox.showerror("Validation Error", "Port must be a valid integer between 1 and 65535.")
                return

            self.videohub_ip = ip_str
            self.videohub_port = port_val
            
            # Commit config adjustments automatically to disk
            self.save_presets_to_file()
            self.update_status_footer()
            settings_dialog.destroy()

        actions_frame = tk.Frame(settings_dialog, bg="#f4f4f4", pady=16, bd=0, highlightthickness=1, highlightbackground="#e0e0e0")
        actions_frame.pack(side=tk.BOTTOM, fill=tk.X)

        save_btn = tk.Button(
            actions_frame, text="Save Configuration", font=("Helvetica Neue", 11, "bold"),
            bg="#161616", fg="#ffffff", activebackground="#393939", activeforeground="#ffffff",
            relief="flat", bd=0, padx=20, pady=10, cursor="hand2"
        )
        save_btn.pack(side=tk.RIGHT, padx=24)
        save_btn.bind("<Button-1>", lambda e: save_network_config())

    def load_presets_from_file(self):
        if not os.path.exists(JSON_FILE):
            with open(JSON_FILE, "w") as f:
                json.dump({}, f)
            return {}
        try:
            with open(JSON_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            messagebox.showerror("File Error", f"Failed to parse {JSON_FILE}:\n{e}")
            return {}

    def save_presets_to_file(self):
        try:
            # Inject stateful properties securely inside an isolated metadata block
            payload = dict(self.presets)
            payload["__network_config__"] = {
                "ip": self.videohub_ip,
                "port": self.videohub_port
            }
            with open(JSON_FILE, "w") as f:
                json.dump(payload, f, indent=4)
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not write configuration payload to file:\n{e}")

    def deploy_salvo(self, name, mapping):
        command = "VIDEO OUTPUT ROUTING:\n"
        for dest, src in mapping.items():
            command += f"{dest} {src}\n"
        command += "\n" 

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((self.videohub_IP, self.videohub_PORT))
                s.recv(4096) 
                s.sendall(command.encode('utf-8'))
            self.status_var.set(f"Successfully deployed: '{name}'")
        except Exception:
            self.status_var.set("Simulated Salvo Deployment Block Triggered")

    def capture_live_matrix(self):
        self.status_var.set("Capturing matrix...")
        self.root.update_idletasks()
        response = ""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((self.videohub_IP, self.videohub_PORT))
                while True:
                    chunk = s.recv(4096).decode('utf-8', errors='ignore')
                    if not chunk: break
                    response += chunk
                    if "VIDEO OUTPUT ROUTING:" in response and "\n\n" in response.split("VIDEO OUTPUT ROUTING:")[1]:
                        break
        except Exception:
            messagebox.showerror("Capture Failed", "Could not reach Videohub network while offline.")
            return

        try:
            routing_section = response.split("VIDEO OUTPUT ROUTING:\n")[1].split("\n\n")[0]
            live_map = {}
            for line in routing_section.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 2: live_map[parts[0]] = parts[1]
        except Exception:
            messagebox.showerror("Data Error", "Could not cleanly isolate active status.")
            return

        preset_name = simpledialog.askstring("Save Matrix Config", "Enter a name descriptor:")
        if preset_name and preset_name.strip():
            self.presets[preset_name.strip()] = live_map
            self.save_presets_to_file()
            self.render_preset_buttons()

    def test_connection(self):
        self.update_status_footer("Syncing Labels...")
        self.root.update_idletasks()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((self.videohub_ip, self.videohub_port))
                self.fetch_hardware_labels()
                messagebox.showinfo("Success", f"Labels successfully pulled from {self.videohub_ip}!")
                self.update_status_footer()
        except Exception:
            self.fetch_hardware_labels()
            messagebox.showwarning("Offline Sync", "Could not reach live hardware route. Loaded simulation defaults instead.")
            self.update_status_footer("Sync Status: Loaded Simulation Map")

if __name__ == "__main__":
    root = tk.Tk()
    app = SalvoApp(root)
    root.mainloop()