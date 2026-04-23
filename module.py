r"""
Training Docs Module - Create and Track Training Guides

This module handles:
- Configuring the training guides folder (browse button in the header bar)
- Creation of new training guide folders
- Browsing existing guides grouped by category
- File management for each guide
- Metadata tracking (category, revision, description)

Requires 'training_docs_dir' to be set in JobDocs settings.

Drag-and-drop diagnostics are written to:
  %TEMP%\jobdocs_training_drag.log
"""

import os
import json
import shutil
import logging
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List

from PyQt6.QtWidgets import (
    QWidget, QTreeWidgetItem, QFileDialog, QAbstractItemView
)
from PyQt6.QtCore import Qt
from PyQt6 import uic

from core.base_module import BaseModule
from shared.utils import open_folder, sanitize_filename


CATEGORIES = ["General", "Safety", "Equipment", "Process", "Quality", "SOP", "Other"]
META_FILENAME = "training_meta.json"

_LOG_PATH = Path(tempfile.gettempdir()) / "jobdocs_training_drag.log"

def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("training_docs.drag")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(_LOG_PATH, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(fh)
    return logger

_log = _setup_logger()


class TrainingDocsModule(BaseModule):
    """Module for creating and managing training guides"""

    def __init__(self):
        super().__init__()
        self._widget = None

        # Create Guide tab widget refs
        self.guide_number_edit = None
        self.title_edit = None
        self.category_combo = None
        self.revision_edit = None
        self.description_edit = None
        self.guide_files_list = None
        self.guide_status_label = None

        # Folder config bar (persistent across tabs)
        self.training_dir_edit = None

        # Browse tab widget refs
        self.search_edit = None
        self.guide_tree = None
        self.guide_files_detail = None
        self.selected_guide_label = None
        self.browse_status_label = None

        # State
        self.guide_files: List[str] = []
        self._selected_guide_path: str | None = None

        _log.info("TrainingDocsModule initialised — log: %s", _LOG_PATH)

    def get_name(self) -> str:
        return "Training Docs"

    def get_order(self) -> int:
        return 90

    def initialize(self, app_context):
        super().initialize(app_context)

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self._widget = self._create_widget()
        return self._widget

    def _get_ui_path(self) -> Path:
        ui_file = Path(__file__).parent / 'ui' / 'training_tab.ui'
        if not ui_file.exists():
            raise FileNotFoundError(f"UI file not found: {ui_file}")
        return ui_file

    def _create_widget(self) -> QWidget:
        widget = QWidget()
        uic.loadUi(str(self._get_ui_path()), widget)

        # ===== Folder Config Bar =====
        self.training_dir_edit = widget.training_dir_edit
        saved_dir = self.app_context.get_setting('training_docs_dir', '')
        if saved_dir:
            self.training_dir_edit.setText(saved_dir)
        widget.browse_dir_btn.clicked.connect(self.browse_training_dir)

        # ===== Create Guide Tab =====
        self.guide_number_edit = widget.guide_number_edit
        self.title_edit = widget.title_edit
        self.category_combo = widget.category_combo
        self.revision_edit = widget.revision_edit
        self.description_edit = widget.description_edit
        self.guide_files_list = widget.guide_files_list
        self.guide_status_label = widget.guide_status_label

        self.category_combo.addItems(CATEGORIES)
        self.guide_files_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        widget.auto_gen_btn.clicked.connect(self.auto_generate_guide_number)
        widget.add_files_btn.clicked.connect(self.browse_add_files)
        widget.remove_file_btn.clicked.connect(self.remove_file)
        widget.create_guide_btn.clicked.connect(self.create_guide)
        widget.clear_form_btn.clicked.connect(self.clear_form)
        widget.open_dir_btn.clicked.connect(self.open_training_dir)

        # Attach drag-and-drop to both the root widget AND the file list widget.
        # Child widgets absorb events and do not propagate to the parent, so the
        # root-only approach is hit-and-miss depending on exactly where the user drops.
        widget.setAcceptDrops(True)
        widget.dragEnterEvent = self._drag_enter
        widget.dropEvent = self._drop_event

        self.guide_files_list.setAcceptDrops(True)
        self.guide_files_list.dragEnterEvent = self._drag_enter
        self.guide_files_list.dropEvent = self._drop_event

        _log.info("Drag-and-drop wired to root widget AND guide_files_list")

        # ===== Browse Tab =====
        self.search_edit = widget.search_edit
        self.guide_tree = widget.guide_tree
        self.guide_files_detail = widget.guide_files_detail
        self.selected_guide_label = widget.selected_guide_label
        self.browse_status_label = widget.browse_status_label

        widget.search_btn.clicked.connect(self.search_guides)
        widget.search_edit.returnPressed.connect(self.search_guides)
        widget.clear_search_btn.clicked.connect(self.clear_search)
        widget.refresh_btn.clicked.connect(self.refresh_guide_tree)
        widget.open_guide_btn.clicked.connect(self.open_selected_guide)
        widget.view_file_btn.clicked.connect(self.open_selected_file)
        self.guide_tree.itemSelectionChanged.connect(self.on_guide_selected)

        self.refresh_guide_tree()
        return widget

    def browse_training_dir(self):
        """Let the user choose the training guides root folder"""
        current = self.app_context.get_setting('training_docs_dir', '')
        chosen = QFileDialog.getExistingDirectory(
            self._widget,
            "Select Training Guides Folder",
            current or ""
        )
        if chosen:
            self.training_dir_edit.setText(chosen)
            self.app_context.set_setting('training_docs_dir', chosen)
            self.app_context.save_settings()
            self.log_message(f"Training docs folder set: {chosen}")
            self.refresh_guide_tree()

    def _get_training_dir(self) -> Path | None:
        dir_path = self.app_context.get_setting('training_docs_dir', '')
        if not dir_path:
            self.show_error(
                "No Folder Set",
                "Training guides folder is not configured.\n\n"
                "Use the Browse button at the top to choose a folder."
            )
            return None
        p = Path(dir_path)
        if not p.exists():
            try:
                p.mkdir(parents=True)
            except OSError as e:
                self.show_error("Directory Error", f"Could not create training guides folder:\n{e}")
                return None
        return p

    # ==================== Create Guide Tab ====================

    def auto_generate_guide_number(self):
        """Auto-generate the next guide number (TG001, TG002, ...)"""
        training_dir = self.app_context.get_setting('training_docs_dir', '')
        highest = 0
        if training_dir and Path(training_dir).exists():
            try:
                for item in Path(training_dir).iterdir():
                    if item.is_dir() and not item.name.startswith('_'):
                        parts = item.name.split('_', 1)
                        prefix = parts[0].upper()
                        if prefix.startswith('TG'):
                            num_str = prefix[2:]
                            if num_str.isdigit():
                                highest = max(highest, int(num_str))
            except OSError:
                pass
        self.guide_number_edit.setText(f"TG{highest + 1:03d}")

    def browse_add_files(self):
        """Open file dialog to add files to the guide"""
        files, _ = QFileDialog.getOpenFileNames(
            self._widget, "Select Files", "", "All Files (*.*)"
        )
        for f in files:
            if f not in self.guide_files:
                self.guide_files.append(f)
                self.guide_files_list.addItem(os.path.basename(f))

    def remove_file(self):
        """Remove selected files from the list"""
        rows = sorted(
            {i.row() for i in self.guide_files_list.selectedIndexes()},
            reverse=True
        )
        for row in rows:
            if 0 <= row < len(self.guide_files):
                self.guide_files_list.takeItem(row)
                del self.guide_files[row]

    # ==================== Drag and Drop ====================

    def _drag_enter(self, event):
        mime = event.mimeData()
        formats = mime.formats()

        _log.info("--- dragEnterEvent fired ---")
        _log.info("  MIME formats available (%d): %s", len(formats), formats)
        _log.info("  hasUrls=%s  hasText=%s  hasHtml=%s",
                  mime.hasUrls(), mime.hasText(), mime.hasHtml())

        if mime.hasUrls():
            urls = mime.urls()
            _log.info("  URLs (%d):", len(urls))
            for u in urls:
                _log.info("    scheme=%r  toLocalFile=%r  toString=%r",
                          u.scheme(), u.toLocalFile(), u.toString())
            event.acceptProposedAction()
            _log.info("  -> ACCEPTED (has URLs)")
        else:
            _log.warning("  -> IGNORED (no URLs — possible Outlook/email drag)")
            _log.warning("     To support email attachments, handle FileGroupDescriptor MIME type")
            event.ignore()

    def _drop_event(self, event):
        mime = event.mimeData()
        formats = mime.formats()

        _log.info("--- dropEvent fired ---")
        _log.info("  MIME formats available (%d): %s", len(formats), formats)

        added = []
        skipped_not_file = []
        skipped_duplicate = []

        if mime.hasUrls():
            for url in mime.urls():
                raw = url.toString()
                local = url.toLocalFile()
                _log.info("  URL: scheme=%r  toString=%r  toLocalFile=%r",
                          url.scheme(), raw, local)

                if not local:
                    _log.warning("    -> toLocalFile() returned empty — skipping (scheme not file://)")
                    skipped_not_file.append(raw)
                    continue

                if not os.path.isfile(local):
                    is_dir = os.path.isdir(local)
                    _log.warning("    -> path is not a file (isdir=%s) — skipping: %r", is_dir, local)
                    skipped_not_file.append(local)
                    continue

                if local in self.guide_files:
                    _log.info("    -> duplicate, already in list — skipping: %r", local)
                    skipped_duplicate.append(local)
                    continue

                self.guide_files.append(local)
                self.guide_files_list.addItem(os.path.basename(local))
                added.append(local)
                _log.info("    -> ADDED: %r", local)
        else:
            _log.warning("  No URLs in drop event — possible Outlook attachment drag")
            _log.warning("  Available formats for future handling: %s", formats)

        _log.info("  Drop summary: added=%d  skipped_not_file=%d  skipped_duplicate=%d",
                  len(added), len(skipped_not_file), len(skipped_duplicate))

        if added:
            self.guide_status_label.setText(
                f"{len(added)} file(s) added via drag-and-drop"
            )
            self.guide_status_label.setStyleSheet("color: green;")
            event.acceptProposedAction()
        else:
            event.ignore()

    # ==================== Guide Creation ====================

    def create_guide(self):
        """Create the training guide folder with metadata and files"""
        guide_num = self.guide_number_edit.text().strip()
        title = self.title_edit.text().strip()
        category = self.category_combo.currentText().strip()
        revision = self.revision_edit.text().strip() or "1.0"
        description = self.description_edit.text().strip()

        if not guide_num or not title:
            self.show_error("Missing Fields", "Guide Number and Title are required.")
            return

        training_dir = self._get_training_dir()
        if training_dir is None:
            return

        folder_name = sanitize_filename(f"{guide_num}_{title}")
        guide_path = training_dir / folder_name

        if guide_path.exists():
            self.show_error(
                "Already Exists",
                f"A guide folder with this name already exists:\n{guide_path}"
            )
            return

        try:
            guide_path.mkdir(parents=True)

            meta = {
                'guide_number': guide_num,
                'title': title,
                'category': category,
                'revision': revision,
                'description': description,
                'created': datetime.now().isoformat(),
                'files': []
            }

            for src_path in self.guide_files:
                dest = guide_path / os.path.basename(src_path)
                if not dest.exists():
                    shutil.copy2(src_path, dest)
                meta['files'].append(os.path.basename(src_path))

            with open(guide_path / META_FILENAME, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2)

            self.app_context.add_to_history('training_guide', {
                'date': datetime.now().isoformat(),
                'guide_number': guide_num,
                'title': title,
                'category': category,
                'revision': revision,
                'path': str(guide_path)
            })
            self.app_context.save_history()

            self.guide_status_label.setText(f"Created: {folder_name}")
            self.guide_status_label.setStyleSheet("color: green;")
            event.acceptProposedAction()
            self.log_message(f"Training guide created: {guide_path}")
            self.show_info("Guide Created", f"Training guide created successfully:\n{guide_path}")
            self.clear_form()
            self.refresh_guide_tree()

        except OSError as e:
            self.show_error("Error", f"Failed to create guide:\n{e}")

    def clear_form(self):
        """Clear all Create Guide form fields"""
        self.guide_number_edit.clear()
        self.title_edit.clear()
        self.category_combo.setCurrentIndex(0)
        self.revision_edit.clear()
        self.description_edit.clear()
        self.guide_files.clear()
        self.guide_files_list.clear()
        if self.guide_status_label:
            self.guide_status_label.setText("")
            self.guide_status_label.setStyleSheet("")

    def open_training_dir(self):
        """Open the training docs directory in file explorer"""
        training_dir = self.app_context.get_setting('training_docs_dir', '')
        if training_dir and Path(training_dir).exists():
            success, error = open_folder(training_dir)
            if not success:
                self.show_error("Error", error or "Could not open folder")
        else:
            self.show_error(
                "No Folder Set",
                "Training guides folder not configured or does not exist.\n\n"
                "Use the Browse button at the top to choose a folder."
            )

    # ==================== Browse Tab ====================

    def refresh_guide_tree(self):
        """Reload the guide tree without a search filter"""
        self._load_guide_tree("")

    def search_guides(self):
        """Filter the guide tree by the search term"""
        self._load_guide_tree(self.search_edit.text().strip())

    def clear_search(self):
        """Clear search box and reload tree"""
        self.search_edit.clear()
        self.refresh_guide_tree()

    def _load_guide_tree(self, search_term: str):
        """Populate the guide tree, grouped by category, with optional search filter"""
        self.guide_tree.clear()
        self.guide_files_detail.clear()
        self._selected_guide_path = None

        training_dir = self.app_context.get_setting('training_docs_dir', '')
        if not training_dir or not Path(training_dir).exists():
            self.browse_status_label.setText("Training docs directory not configured.")
            return

        term = search_term.lower()
        category_items: dict[str, QTreeWidgetItem] = {}
        guide_count = 0

        try:
            for item in sorted(Path(training_dir).iterdir()):
                if not item.is_dir() or item.name.startswith('_'):
                    continue

                meta_file = item / META_FILENAME
                if meta_file.exists():
                    try:
                        with open(meta_file, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                        category = meta.get('category', 'General')
                        guide_num = meta.get('guide_number', '')
                        title = meta.get('title', item.name)
                        revision = meta.get('revision', '')
                        display = f"{guide_num} – {title}"
                        if revision:
                            display += f"  (Rev {revision})"
                    except (OSError, json.JSONDecodeError):
                        category = 'General'
                        display = item.name
                else:
                    category = 'General'
                    display = item.name

                if term and term not in display.lower() and term not in category.lower():
                    continue

                if category not in category_items:
                    cat_item = QTreeWidgetItem([category])
                    cat_item.setData(0, Qt.ItemDataRole.UserRole, None)
                    self.guide_tree.addTopLevelItem(cat_item)
                    category_items[category] = cat_item

                guide_item = QTreeWidgetItem([display])
                guide_item.setData(0, Qt.ItemDataRole.UserRole, str(item))
                category_items[category].addChild(guide_item)
                guide_count += 1

        except OSError as e:
            self.browse_status_label.setText(f"Error reading directory: {e}")
            return

        self.guide_tree.expandAll()

        label = f"{guide_count} guide(s)"
        if search_term:
            label += f" matching '{search_term}'"
        self.browse_status_label.setText(label)

    def on_guide_selected(self):
        """Populate the file details panel when a guide is selected"""
        self.guide_files_detail.clear()
        self._selected_guide_path = None

        items = self.guide_tree.selectedItems()
        if not items:
            self.selected_guide_label.setText("")
            return

        item = items[0]
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            self.selected_guide_label.setText("Select a guide, not a category")
            self.selected_guide_label.setStyleSheet("color: orange;")
            return

        self._selected_guide_path = path
        self.selected_guide_label.setText(f"Selected: {item.text(0)}")
        self.selected_guide_label.setStyleSheet("color: green;")

        try:
            guide_path = Path(path)
            for f in sorted(guide_path.iterdir()):
                if f.is_file() and f.name != META_FILENAME:
                    self.guide_files_detail.addItem(f.name)
        except OSError:
            pass

    def open_selected_guide(self):
        """Open the selected guide's folder in file explorer"""
        if not self._selected_guide_path:
            self.open_training_dir()
            return

        if Path(self._selected_guide_path).exists():
            success, error = open_folder(self._selected_guide_path)
            if not success:
                self.show_error("Error", error or "Could not open folder")
        else:
            self.show_error("Not Found", f"Folder no longer exists:\n{self._selected_guide_path}")
            self.refresh_guide_tree()

    def open_selected_file(self):
        """Open the file selected in the detail list"""
        if not self._selected_guide_path:
            return
        row = self.guide_files_detail.currentRow()
        if row < 0:
            return
        file_name = self.guide_files_detail.item(row).text()
        file_path = Path(self._selected_guide_path) / file_name
        if file_path.exists():
            import subprocess
            try:
                os.startfile(str(file_path))
            except AttributeError:
                subprocess.Popen(['xdg-open', str(file_path)])
        else:
            self.show_error("Not Found", f"File no longer exists:\n{file_path}")

    def cleanup(self):
        self.guide_files.clear()
