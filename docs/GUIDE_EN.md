# llm-gateway Application User Guide

## What is this application for?

The llm-gateway application lets you automatically process a large number of tasks using artificial intelligence models. You provide your data (images, texts, CSV files, URLs) and an instruction. The application selects the most suitable model, checks the quality of each response, and presents you with a complete report.

## How to use it

### 1. Open the application

Launch the application by typing `python -m llm_gateway.gui` in a terminal, or double-click the shortcut if you have one.

A window opens with three tabs.

### 2. Prepare your data (tab "Prepare data")

- **Source type**: choose what you want to process (folder of images, folder of text files, CSV file, or list of URLs).
- **Location**: click "Browse" and select your folder or file.
- **Instruction**: keep the default instruction or adapt it (e.g., "Extract the key figures from this chart").
- **Output file**: specify where to save the task file (`.jsonl` format).
- Click "Generate task file". A message confirms the number of tasks created.

### 3. Launch processing (tab "Launch processing")

- **Input file**: select the `.jsonl` file you just created.
- **Output file**: specify where to save the results.
- **Configuration**: select the `config/models.yaml` file (provided with the application).
- **Maximum budget**: optional, in euros. The application stops if the estimated cost exceeds this amount.
- Click "Launch processing". A progress bar shows the progress.

### 4. View results (tab "View results")

- **Summary**: the number of approved tasks, tasks to review, failed tasks, total cost, and distribution by model.
- **To review**: a list of tasks whose response did not pass quality control. For each, you see the produced response, the reason for flagging, and two buttons: "Accept" or "Reject".
- **All**: the complete list of tasks with their status.

## What to do when something is flagged

Open the "To review" tab. Each line corresponds to a task whose response is considered uncertain. Read the response and the reason ("inconsistent number", "suspected hallucination", etc.). Decide: accept the response, or reject it. Your decision is recorded.

## What you don't have to do

- Write JSON files manually.
- Understand what a language model is.
- Manage API keys (this is done once, by the person who installs the application).

## Need help?

- Run `llm-gateway doctor --config config/models.yaml` to check that everything is in place.
- See the `README.md` for technical aspects.
- If you encounter a problem, check that the `config/models.yaml` file exists and that the recommended Ollama models are installed (`llm-gateway setup --config config/models.yaml`).