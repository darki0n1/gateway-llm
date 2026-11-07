# gateway-llm Application User Guide

## What is this application for?

The gateway-llm application automatically processes a large number of tasks using artificial intelligence models. You provide data (images, texts, CSV files, URLs) and an instruction. The application selects the appropriate model, verifies the quality of each response, and produces a complete report.

## What you see when you open it

Open the application by typing `python -m gateway_llm.gui` in a terminal, or by double-clicking the shortcut if you have one.

A window appears with four tabs:

- **Configuration**
- **Prepare data**
- **Launch processing**
- **View results**

On the very first launch, the application first asks about the **execution mode** (see next section), then opens the **Configuration** tab to know where your access keys to AI services are stored. Once these two steps are done, they are not requested again.

## 1. Execution mode (first launch only)

Before configuring keys, the application asks how you want to use it. This choice determines which models will be used and possibly downloaded.

A window opens with four options:

- **100% cloud** — uses only online AI services (Groq, Mistral, OpenRouter, Google…). No model is installed on your machine. Ideal if you have a good connection and API keys.
- **100% local** — downloads the best models that can run on your machine, based on its memory and disk space. No data leaves your computer. Ideal for privacy.
- **Hybrid** — uses the models already on your machine, and complements with the cloud when a better online model is available. Best quality/cost compromise.
- **Default (recommended)** — downloads only the few lightweight models needed for the application's basic operation (routing, classification). You can always add more models later.

Choose the option that fits your use case, then click **Validate**. You can change your mind later by editing the `~/.gateway-llm/config.yaml` file (ask for help if needed).

**Tip**: if you don't know what to choose, pick **Default**. It's the simplest and fastest to set up.

## 2. Access key configuration (first launch only)

The application needs access to external AI services or to models installed on your machine. These services require access keys. These keys must be stored in a secure place, never in a visible text file.

The Configuration tab offers several options:

- **PowerShell Vault** — the recommended solution on Windows. Keys are stored in the secret manager built into Windows.
- **1Password** — if you already use this password manager.
- **HashiCorp Vault, AWS Secrets Manager, Azure Key Vault** — if your organization uses one of these services.
- **Environment variables** — not recommended, as unencrypted.

Choose the option that fits your situation. Click **Save configuration**, then **Test connection** to verify everything works. The application then tells you whether the keys are accessible.

**If you are in 100% local mode**, you can skip this step: no API keys are needed.

## 3. Prepare data

This tab turns your files into a list of tasks that the application can process.

- **Source type**: select what you want to process.
  - Folder of images (screenshots, charts, tables)
  - Folder of text files
  - File(s) CSV — one or more, all columns will be read by the model
  - List of URLs
  - **Mixed** — to combine images, texts and CSV at once
- **Location(s)**: click **Add…** to choose your files or folders. You can add several. **Drag & drop** also works: drag your files from Windows Explorer to the list.
- **Remove / Clear**: to remove a selected item or clear everything.
- **Instruction**: what you ask the model. For example:
  - For a folder of images: "Analyze this image and describe what you see."
  - To extract figures from a chart: "Extract the key figures from this chart."
  - For a CSV: "Here is a table. Compute the total revenue." (the model reads all columns and picks the relevant ones)
  - In **Mixed** mode: "With this table and these KPIs, determine the right decision to make in this text file."
- **Output file**: specify where to save the task list (`.jsonl` extension).

Click **Generate task file**. A message confirms the number of tasks prepared.

**CSV tip**: no need to pick a column anymore. The application sends **the entire table** to the model, which understands on its own which columns matter for your instruction. This enables questions like "compute the total revenue" or "which row has the highest turnover" without any extra configuration.

## 4. Launch processing

This tab sends the tasks to the AI models.

- **Input file**: select the `.jsonl` file prepared in the previous step.
- **Results file**: specify where to save the responses. If you leave it empty, a `results.jsonl` file will be created next to your input file.
- **Advanced options** (hidden by default, "Show advanced options" button):
  - **Configuration**: leave empty to use the built-in configuration. Useful only for advanced users who want a custom models file.
  - **Maximum budget**: optional. Specify an amount in euros so the application stops if the cost exceeds this limit.

Click **Launch processing**. A progress bar shows the progress, and a **live log** area displays everything happening: config loading, possible model downloads, task progress, cumulative cost, etc.

**Cancel**: if you change your mind, click the **Cancel** button next to "Launch processing". The application finishes the current task then stops cleanly, without losing already-produced results.

If processing is interrupted (outage, closing the window), relaunch it with the same results file: the application resumes where it stopped.

## 5. View results

This tab displays what was produced. After a batch, **it opens automatically** with the results file already loaded and refreshed every 2 seconds while the batch is running.

- **Summary**: number of approved tasks, tasks to review, failed tasks, total cost.
- **To review**: list of tasks whose response did not pass the automatic quality check. Each line shows the task identifier and the reason for flagging. Click a line to see the response produced (displayed in **Markdown**: headings, bold, lists, code, etc.) and decide: **Accept** or **Reject**.
- **All**: complete list of tasks with their status, the model used, and the cost.

## What to do when something is flagged

Open the **To review** tab. Each flag indicates why the response was considered uncertain: "number inconsistent with source", "suspected hallucination", "citation not verified".

Read the response produced, compare it to the original document or image, then decide: **Accept** (the response is validated, it joins the final results) or **Reject** (the response is discarded).

This is the only moment your personal judgment is required. All other tasks are processed automatically.

## Processing screenshots and images

The application can analyze images: screenshots, financial charts, dashboards, scanned documents.

To do so:

1. In the **Prepare data** tab, choose **Folder of images** (or **Mixed** if you also have text or CSV to combine).
2. Add the folder or files containing your images (supported formats: `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`).
3. Adapt the instruction: for example "Extract the quarterly revenue and operating margin shown on this chart."
4. Click **Generate task file**, then launch processing normally.

**Important privacy note**: if your images contain sensitive data (non-public figures, personal information, visible identifiers), choose **100% local** or **Hybrid** mode and verify that the default sensitivity is set to `confidential`. This ensures the images are processed only by a local model, with no transmission over the Internet.

## Processing a CSV with multiple columns

The application sends **the entire table** (all columns and all rows) to the model, in batches of 500 rows. You don't have to pick a column.

Examples of instructions that work:

- "Compute the total revenue by multiplying the 'price' column by the 'sales' column."
- "Summarize the main information from this table."
- "Which row has the highest turnover?"
- "Are there any inconsistent values in this table?"

**Multiple CSVs**: you can add several CSV files at once. Each will be processed separately, and results will be concatenated in the output file.

## Combining multiple file types (Mixed mode)

If you want a single processing to consider an image, a text file and a CSV, choose **Mixed** in the source type, then add all your files.

Concrete example: you have a chart (`kpi.png`), a quarterly report (`report.txt`) and a sales table (`sales.csv`). You write the following instruction:

> "With this table and these KPIs, determine the right decision to make in this text file."

The application will:
- send the image to the multimodal model;
- include the text of the report and the CSV table in the prompt;
- produce a single answer that synthesizes everything.

## What you don't have to do

- Manually write configuration files.
- Understand how AI models work internally.
- Choose which model to use: the application does this automatically based on the nature of each task and your hardware.
- Install technical components: the application downloads on its own the local models it needs and, if necessary, Chromium for its internal tools.
- Manually download models: it's automatic based on your execution mode.

## Need help

- To check that everything is in place: `gateway-llm doctor` in a terminal.
- To install missing local models: `gateway-llm setup`.
- For technical aspects: see the `README.md` file.
- If an error appears in the live log, it usually indicates the cause. The most common problems are: a missing model (the application downloads it automatically), a file not found (check the path), or insufficient disk space (models take several gigabytes).