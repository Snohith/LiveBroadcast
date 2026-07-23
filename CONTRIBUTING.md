# Contributing to Live Cricket Score API & Broadcast Package

First off, thank you for considering contributing to this project! It's open-source projects like this that make the developer community an amazing place to build, learn, and create.

---

## 🚀 How to Contribute

### Reporting Bugs

Before creating a bug report, please check existing issues to avoid duplicates. When creating a bug report, include as much detail as possible:

- **Use a clear and descriptive title**
- **Describe the exact steps to reproduce the issue**
- **Provide specific examples or CREX match keys (e.g. `12UZ`)**
- **Include error logs or browser console screenshots if applicable**
- **Mention your Python version and Operating System**

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating a feature request, please:

- **Use a clear and descriptive title**
- **Provide a step-by-step explanation of the suggested feature**
- **Explain why this enhancement would be useful to the community**

---

## 🛠️ Local Development Setup

1. **Fork the Repository** on GitHub.
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/your-username/live-cricket-score-api.git
   cd live-cricket-score-api
   ```
3. **Set up virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
4. **Run the local dev server**:
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 6021 --reload
   ```

---

## 📜 Pull Request Process

1. Create a new topic branch from `main`:
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. Make your code changes and test locally by fetching live scores and rendering the overlay.
3. Ensure code formatting is clean and adheres to PEP 8 standards.
4. Commit your changes with a clear commit message:
   ```bash
   git commit -m "feat: add real-time strike rate calculator"
   ```
5. Push to your fork and submit a **Pull Request** targeting the `main` branch.
6. Provide a detailed description in your PR of what was added or fixed.

---

## 🎨 Style Guidelines

- **Python**: Follow [PEP 8](https://peps.python.org/pep-0008/) naming conventions.
- **Frontend / HTML**: Keep Tailwind CSS classes organized and maintain clean semantic HTML formatting. Ensure backwards compatibility for browser overlay state keybinds (`0`, `1`, `2`, `3`).

Thank you for helping improve the project!
