# llm-gateway Application User Guide

## What is this application for?

The llm-gateway application automatically processes a large number of tasks using artificial intelligence models. You provide data (images, texts, CSV files, URLs) and an instruction. The application selects the appropriate model, verifies the quality of each response, and produces a complete report.

## What you see when you open it

Open the application by typing `python -m llm_gateway.gui` in a terminal, or by double-clicking the shortcut if you have one.

A window appears with four tabs:

- **Configuration**
- **Prepare data**
- **Launch processing**
- **View results**

On first launch, the **Configuration** tab opens automatically, because the application needs to know where your access keys to AI services are stored. Once this step is done, it is not requested again.

## 1. Configuration (first time only)

The application needs access to external AI services or to models installed on your machine. These services require access keys. These keys must be stored in a secure place, never in a visible text file.

The Configuration tab offers several options:

- **PowerShell Vault** — the recommended solution on Windows. Keys are stored in the secret manager built into Windows.
- **1Password** — if you already use this password manager.
- **HashiCorp Vault, AWS Secrets Manager, Azure Key Vault** — if your organization uses one of these services.
- **Environment variables** — not recommended, as unencrypted.

Choose the option that fits your situation. Click **Save configuration**, then **Test connection** to verify everything works. The application then tells you whether the keys are accessible.

## 2. Prepare data

This tab turns your files into a list of tasks that the application can process.

- **Source type**: select what you want to process.
  - Folder of images (screenshots, charts, tables)
  - Folder of text files
  - CSV file
  - List of URLs
- **Location**: click **Browse** and select your folder or file.
- **CSV column**: fill in only if you chose a CSV file. Specify the column name containing the text to process.
- **Instruction**: what you ask the model. For a folder of images, the default instruction is "Analyze this image and describe what you see." To extract figures from a chart, replace it with "Extract the key figures from this chart."
- **Output file**: specify where to save the task list (`.jsonl` extension).

Click **Generate task file**. A message confirms the number of tasks prepared.

## 3. Launch processing

This tab sends the tasks to the AI models.

- **Input file**: select the `.jsonl` file prepared in the previous step.
- **Results file**: specify where to save the responses.
- **Configuration**: select the `config/models.yaml` file provided with the application. It contains the list of available models and selection rules.
- **Maximum budget**: optional. Specify an amount in euros so the application stops if the cost exceeds this limit.

Click **Launch processing**. A progress bar shows the progress. Depending on the number of tasks and the models used, processing may take from a few minutes to several hours.

If processing is interrupted (outage, closing the window), relaunch it with the same results file: the application resumes where it stopped.

## 4. View results

This tab displays what was produced.

- **Summary**: number of approved tasks, tasks to review, failed tasks, total cost, distribution by model.
- **To review**: list of tasks whose response did not pass the automatic quality check. Each line shows the task identifier and the reason for flagging. Click a line to see the response produced and decide: **Accept** or **Reject**.
- **All**: complete list of tasks with their status, the model used, and the cost.

## What to do when something is flagged

Open the **To review** tab. Each flag indicates why the response was considered uncertain: "number inconsistent with source", "suspected hallucination", "citation not verified".

Read the response produced, compare it to the original document or image, then decide: **Accept** (the response is validated, it joins the final results) or **Reject** (the response is discarded).

This is the only moment your personal judgment is required. All other tasks are processed automatically.

## Processing screenshots and images

The application can analyze images: screenshots, financial charts, dashboards, scanned documents.

To do so:

1. In the **Prepare data** tab, choose **Folder of images**.
2. Select the folder containing your images (supported formats: `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`).
3. Adapt the instruction: for example "Extract the quarterly revenue and operating margin shown on this chart."
4. Click **Generate task file**, then launch processing normally.

**Important privacy note**: if your images contain sensitive data (non-public figures, personal information, visible identifiers), open the Configuration tab before launching processing and verify that the default sensitivity is set to `confidential`. This ensures the images are processed only by a local model, with no transmission over the Internet.

## What you don't have to do

- Manually write configuration files.
- Understand how AI models work internally.
- Choose which model to use: the application does this automatically based on the nature of each task.
- Install technical components: the person who installed the application handled this once.

## Need help

- To check that everything is in place: `llm-gateway doctor --config config/models.yaml` in a terminal.
- To install missing local models: `llm-gateway setup --config config/models.yaml`.
- For technical aspects: see the `README.md` file.
- If an error appears, it usually indicates the cause. The most common problems are: a missing model, a file not found, or insufficient disk space.