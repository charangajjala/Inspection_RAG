import streamlit as st
import os
import json
import glob
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === Google Sheets Setup ===
SHEET_NAME = "Expert_Review_Sheet"

# === Load credentials securely from Streamlit secrets ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
service_account_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
credentials = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
gc = gspread.authorize(credentials)
spreadsheet = gc.open(SHEET_NAME)

# === Paths ===
CHECKLIST_DIR = "final_checklists"
REPORT_DIR = "reports"
TRUTH_PATH = "Actions_final.json"

# === Load ground truth mapping ===
with open(TRUTH_PATH) as f:
    ground_truth_data = json.load(f)

question_to_action = {
    item["Question"].strip(): [a["Action"] for a in item.get("Required Actions", []) if "Action" in a]
    for item in ground_truth_data
}

# === Streamlit Setup ===
st.set_page_config(page_title="Safety Review Portal", layout="wide")
st.markdown("<h1 style='font-size: 2.8em;'>🏗️ Scaffold Safety Review Portal</h1>", unsafe_allow_html=True)

# === Username-only Login ===
with st.form("login_form"):
    username = st.text_input("Username", placeholder="Enter your username")
    login_btn = st.form_submit_button("Start Review")

if not username.strip():
    st.warning("Please enter your username to continue.")
    st.stop()

expert_id = username.strip()
st.success(f"Logged in as {expert_id}")
st.markdown("---")

# === Load checklist/report files ===
checklist_files = sorted(glob.glob(f"{CHECKLIST_DIR}/checklist_*.md"))
report_files = sorted(glob.glob(f"{REPORT_DIR}/checklist_*.json"))

file_pairs = [
    (os.path.basename(path).replace(".md", ""), path, os.path.join(REPORT_DIR, os.path.basename(path).replace(".md", ".json")))
    for path in checklist_files
    if os.path.exists(os.path.join(REPORT_DIR, os.path.basename(path).replace(".md", ".json")))
]

# === Navigation State ===
if "index" not in st.session_state:
    st.session_state.index = 0

max_index = len(file_pairs) - 1
index = st.session_state.index

# === Create Expert Sheet if Needed ===
try:
    worksheet = spreadsheet.worksheet(expert_id)
except gspread.exceptions.WorksheetNotFound:
    worksheet = spreadsheet.add_worksheet(title=expert_id, rows="100", cols="5")
    worksheet.append_row(["expert", "combination", "score", "comment", "timestamp"])

existing_rows = worksheet.get_all_values()
submitted_ids = [row[1] for row in existing_rows[1:]]

# === Progress Display ===
st.markdown(f"<p style='font-size: 1.4em;'>🧮 Progress: <b>{len(submitted_ids)}</b> / <b>{len(file_pairs)}</b></p>", unsafe_allow_html=True)
st.progress(len(submitted_ids) / len(file_pairs))

# === Current File ===
base_name, checklist_path, report_path = file_pairs[index]
submitted = "✅ Submitted" if base_name in submitted_ids else "❌ Not Submitted"
status_color = "#28a745" if base_name in submitted_ids else "#dc3545"

st.markdown(
    f"<h2 style='font-size: 2em;'>📂 Reviewing: {base_name} "
    f"<span style='font-size: 0.7em; color: {status_color};'>({submitted})</span></h2>",
    unsafe_allow_html=True
)

# === Checklist Parsing ===
with open(checklist_path, "r") as f:
    checklist_md = f.read()

false_items = []
for line in checklist_md.splitlines():
    if ": False" in line:
        q = line.split(":")[0].replace("- **", "").replace("**", "").strip()
        false_items.append(q)

st.markdown("<h3 style='color:#dc3545; font-size: 1.6em;'>❌ Non-Compliant Checklist Items</h3>", unsafe_allow_html=True)
if false_items:
    for q in false_items:
        st.markdown(f"<p style='font-size: 1.3em;'>• {q}</p>", unsafe_allow_html=True)
else:
    st.markdown("<p><i>No non-compliant items found.</i></p>", unsafe_allow_html=True)

# === Display Report ===
st.markdown("### 📄 Generated Report (Simplified View)")
with open(report_path, "r") as f:
    try:
        report_data = json.load(f)
        if isinstance(report_data, dict):
            findings = report_data.get("detailed_findings", [])
            for finding in findings:
                checklist_item = finding.get("checklist_item", None)
                action_items = finding.get("action_items", [])
                if checklist_item:
                    st.markdown(f"<h4 style='font-size: 1.4em; color:#003366;'>{checklist_item}</h4>", unsafe_allow_html=True)
                    for item in action_items:
                        st.markdown(f"<p style='font-size: 1.2em;'>• {item}</p>", unsafe_allow_html=True)
        else:
            st.markdown(f"<pre>{str(report_data)}</pre>", unsafe_allow_html=True)
    except Exception as e:
        st.markdown(f"<pre>Error loading report: {e}</pre>", unsafe_allow_html=True)

# === Ground Truth Actions ===
st.markdown("### 🧾 Ground Truth Actions")
if false_items:
    for q in false_items:
        actions = question_to_action.get(q, [])
        if actions:
            st.markdown(f"<h4 style='font-size: 1.3em; color:#004085;'>{q}</h4>", unsafe_allow_html=True)
            for a in actions:
                st.markdown(f"<p style='font-size: 1.2em;'>• {a}</p>", unsafe_allow_html=True)
else:
    st.markdown("<p>No matching ground truth actions found.</p>", unsafe_allow_html=True)

# === Review Form ===
score = st.radio("Expert Evaluation Score", [1, 0], format_func=lambda x: "✅ Acceptable" if x == 1 else "❌ Unacceptable")
comment = st.text_area("Optional Comments", height=100)

if st.button("Submit Review"):
    timestamp = datetime.now().isoformat()
    updated = False
    for i, row in enumerate(existing_rows):
        if i == 0:
            continue
        if row[1] == base_name:
            worksheet.update(f"C{i+1}", [[score]])
            worksheet.update(f"D{i+1}", [[comment]])
            worksheet.update(f"E{i+1}", [[timestamp]])
            updated = True
            break
    if not updated:
        worksheet.append_row([expert_id, base_name, score, comment, timestamp])
    st.success("✅ Review submitted!")
    st.rerun()

# === Navigation Buttons ===
col1, col2 = st.columns(2)
with col1:
    if st.button("⬅️ Previous") and index > 0:
        st.session_state.index -= 1
        st.rerun()
with col2:
    if st.button("Next ➡️") and index < max_index:
        st.session_state.index += 1
        st.rerun()
