# Personal MacroBot 

A high-performance desktop automation platform built from scratch in Python using **CustomTkinter**, **OpenCV**, and **PyAutoGUI**. 

This tool was designed to automate trivial, repetitive tasks while incorporating anti-detection mechanics, human-like mouse trajectories, and intelligent visual template matching.

## Features
* **Visual Snip & Search:** Uses OpenCV template matching to scan the desktop for specific graphical assets dynamically.
* **Organic Input Emulation:** Implements Gaussian/Normal distribution scatter algorithms for mouse clicks to avoid pixel-perfect detection vectors.
* **Dynamic Easing Curves:** Simulates authentic cursor velocity changes (acceleration and deceleration curves).
* **Asynchronous Execution:** Runs loops on an independent, non-blocking background execution thread.

## Getting Started

### Prerequisites
Ensure you have Python installed, then run:
```bash
pip install customtkinter pyautogui opencv-python numpy pillow pynput