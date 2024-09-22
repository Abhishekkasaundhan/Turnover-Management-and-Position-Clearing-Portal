import tkinter as tk
from tkinter import messagebox
import subprocess
import webbrowser
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
import os

def start_flask_app():
    try:
        script_path = 'flask_app.py'
        if not os.path.exists(script_path):
            messagebox.showerror("Error", f"File not found: {script_path}")
            return
        subprocess.Popen(['python', script_path], shell=True)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to start Flask app: {e}")

def open_browser():
    webbrowser.open('http://192.168.0.186:8080')

def on_closing():
    if messagebox.askokcancel("Quit", "Do you want to quit?"):
        root.destroy()

root = tk.Tk()
root.title("TurnOver & Position ")

# Center the window on the screen
window_width = 800
window_height = 600
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
position_top = int(screen_height / 2 - window_height / 2)
position_right = int(screen_width / 2 - window_width / 2)
root.geometry(f"{window_width}x{window_height}+{position_right}+{position_top}")

frame = tk.Frame(root, bg="white")
frame.place(relwidth=1, relheight=1)

# Create and animate the plot
fig, ax = plt.subplots()
x = np.linspace(0, 2 * np.pi, 100)
line, = ax.plot(x, np.sin(x))

def animate(i):
    line.set_ydata(np.sin(x + i / 10.0))
    return line,

ani = FuncAnimation(fig, animate, interval=50, blit=True)

canvas = FigureCanvasTkAgg(fig, master=frame)
canvas.draw()
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

button_frame = tk.Frame(root)
button_frame.pack(pady=20)

open_browser_button = tk.Button(button_frame, text="Open Browser", command=open_browser)
open_browser_button.pack(side=tk.LEFT, padx=10)

start_flask_app()

root.protocol("WM_DELETE_WINDOW", on_closing)

root.mainloop()