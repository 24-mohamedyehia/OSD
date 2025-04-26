import sys
import os
import json
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QLineEdit, QPushButton, QComboBox, QFileDialog, 
                            QProgressBar, QTextEdit, QTabWidget, QTableWidget, QTableWidgetItem,
                            QCheckBox, QMessageBox, QSystemTrayIcon, QMenu)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QAction

# Import the actual yt-dlp library
import yt_dlp

# Download worker thread
class DownloadWorker(QThread):
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(str, bool)
    log_signal = pyqtSignal(str)
    
    def __init__(self, url, output_path, format_type, quality):
        super().__init__()
        self.url = url
        self.output_path = output_path
        self.format_type = format_type
        self.quality = quality
        self.is_cancelled = False
        
    def run(self):
        try:
            self.log_signal.emit(f"Starting download of {self.url}")
            
            # Configure yt-dlp options
            options = {
                'format': self._get_format_string(),
                'outtmpl': os.path.join(self.output_path, '%(title)s.%(ext)s'),
                'progress_hooks': [self._progress_hook],
                'quiet': True,
                'no_warnings': True,
                'socket_timeout': 30,
                'retries': 3,
            }
            
            # Use actual yt-dlp library
            self.log_signal.emit("Extracting video information...")
            
            # Check if output directory exists and is writable
            if not os.path.exists(self.output_path):
                try:
                    os.makedirs(self.output_path, exist_ok=True)
                    self.log_signal.emit(f"Created output directory: {self.output_path}")
                except Exception as e:
                    self.log_signal.emit(f"Cannot create output directory: {str(e)}")
                    self.finished_signal.emit(self.url, False)
                    return
            
            if not os.access(self.output_path, os.W_OK):
                self.log_signal.emit(f"No write permission for directory: {self.output_path}")
                self.finished_signal.emit(self.url, False)
                return
            
            # Use the actual yt-dlp library
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(self.url, download=True)
                
                if not self.is_cancelled:
                    if "entries" in info:  # It's a playlist
                        self.log_signal.emit(f"Successfully downloaded playlist: {info.get('title', 'Unknown')}")
                    else:  # It's a single video
                        self.log_signal.emit(f"Successfully downloaded: {info.get('title', 'Unknown')}")
                    
                    self.finished_signal.emit(self.url, True)
                    
        except Exception as e:
            self.log_signal.emit(f"Error during download: {str(e)}")
            self.finished_signal.emit(self.url, False)
    
    def _progress_hook(self, d):
        if d['status'] == 'downloading':
            try:
                # Calculate percentage
                total_bytes = d.get('total_bytes')
                downloaded_bytes = d.get('downloaded_bytes', 0)
                
                if total_bytes:
                    progress = int(downloaded_bytes / total_bytes * 100)
                    self.progress_signal.emit(progress, "Downloading")
                elif d.get('_percent_str'):
                    # Fallback to percent string if available
                    p = d.get('_percent_str', '0%').replace('%', '')
                    progress = int(float(p))
                    self.progress_signal.emit(progress, "Downloading")
                
                # Emit download speed and ETA information
                speed = d.get('speed', 0)
                eta = d.get('eta', 0)
                
                if speed and eta:
                    speed_str = self._format_size(speed) + "/s"
                    self.log_signal.emit(f"Downloading at {speed_str}, ETA: {eta} seconds")
                    
            except Exception as e:
                self.log_signal.emit(f"Progress calculation error: {str(e)}")
                
        elif d['status'] == 'finished':
            self.log_signal.emit(f"Download finished, now converting...")
    
    def _get_format_string(self):
        if self.format_type == "Video (MP4)":
            if self.quality == "1080p":
                return "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
            elif self.quality == "720p":
                return "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
            elif self.quality == "480p":
                return "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
            else:  # 360p
                return "bestvideo[height<=360]+bestaudio/best[height<=360]/best"
        else:  # Audio (MP3)
            if self.quality == "192 kbps":
                return "bestaudio/best"
            elif self.quality == "128 kbps":
                return "bestaudio/best"
            else:  # 96 kbps
                return "bestaudio/best"
    
    def cancel(self):
        self.is_cancelled = True
        
    def _format_size(self, bytes):
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024:
                return f"{bytes:.2f} {unit}"
            bytes /= 1024
        return f"{bytes:.2f} TB"

# Download Queue Item
class DownloadItem:
    def __init__(self, url, output_path, format_type, quality):
        self.url = url
        self.output_path = output_path
        self.format_type = format_type
        self.quality = quality
        self.status = "Queued"
        self.progress = 0
        self.worker = None
        self.title = "Unknown"
        self.date_added = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Main Application Window
class YTDownloaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Application settings
        self.settings = QSettings("OSD", "settings")
        self.download_history = []
        self.download_queue = []
        self.current_download = None
        self.is_dark_mode = self.settings.value("dark_mode", False, type=bool)
        
        # Load download history
        self.load_history()
        
        # Setup UI
        self.setWindowTitle("OSD")
        self.setMinimumSize(900, 600)
        
        # Create system tray icon
        self.setup_tray_icon()
        
        # Create main widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # Create tab widget
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)
        
        # Create tabs
        self.setup_download_tab()
        self.setup_queue_tab()
        self.setup_history_tab()
        self.setup_settings_tab()
        
        # Apply theme
        self.apply_theme()
        
        # Setup drag and drop
        self.setAcceptDrops(True)
        
        # Show the window
        self.show()
    
    def setup_tray_icon(self):
        # In a real app, you would use a real icon
        self.tray_icon = QSystemTrayIcon(self)
        tray_menu = QMenu()
        
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.quit)
        tray_menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.setToolTip("OSD")
        self.tray_icon.show()
    
    def setup_download_tab(self):
        download_tab = QWidget()
        layout = QVBoxLayout(download_tab)
        
        # URL input section
        url_layout = QHBoxLayout()
        url_label = QLabel("YouTube URL:")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter YouTube video or playlist URL")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        layout.addLayout(url_layout)
        
        # Output directory section
        dir_layout = QHBoxLayout()
        dir_label = QLabel("Save to:")
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("Select download directory")
        self.dir_input.setText(self.settings.value("default_directory", "", type=str))
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_directory)
        dir_layout.addWidget(dir_label)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(browse_btn)
        layout.addLayout(dir_layout)
        
        # Format and quality selection
        format_layout = QHBoxLayout()
        
        format_label = QLabel("Format:")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Video (MP4)", "Audio (MP3)"])
        self.format_combo.currentIndexChanged.connect(self.update_quality_options)
        
        quality_label = QLabel("Quality:")
        self.quality_combo = QComboBox()
        
        # Set default format from settings
        default_format = self.settings.value("default_format", "Video (MP4)", type=str)
        default_index = 0 if default_format == "Video (MP4)" else 1
        self.format_combo.setCurrentIndex(default_index)
        
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)
        format_layout.addWidget(quality_label)
        format_layout.addWidget(self.quality_combo)
        layout.addLayout(format_layout)
        
        # Update quality options based on default format
        self.update_quality_options()
        
        # Download button
        self.download_btn = QPushButton("Add to Queue")
        self.download_btn.clicked.connect(self.add_to_queue)
        layout.addWidget(self.download_btn)
        
        # Progress section
        progress_layout = QVBoxLayout()
        progress_label = QLabel("Download Progress:")
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        
        progress_layout.addWidget(progress_label)
        progress_layout.addWidget(self.progress_bar)
        layout.addLayout(progress_layout)
        
        # Log section
        log_layout = QVBoxLayout()
        log_label = QLabel("Log:")
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        
        log_layout.addWidget(log_label)
        log_layout.addWidget(self.log_text)
        layout.addLayout(log_layout)
        
        self.tabs.addTab(download_tab, "Download")
    
    def setup_queue_tab(self):
        queue_tab = QWidget()
        layout = QVBoxLayout(queue_tab)
        
        # Queue table
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(6)
        self.queue_table.setHorizontalHeaderLabels(["Title", "URL", "Format", "Quality", "Progress", "Status"])
        self.queue_table.horizontalHeader().setStretchLastSection(True)
        
        # Queue controls
        controls_layout = QHBoxLayout()
        self.start_queue_btn = QPushButton("Start Queue")
        self.start_queue_btn.clicked.connect(self.start_queue)
        
        self.pause_queue_btn = QPushButton("Pause Queue")
        self.pause_queue_btn.clicked.connect(self.pause_queue)
        self.pause_queue_btn.setEnabled(False)
        
        self.remove_item_btn = QPushButton("Remove Selected")
        self.remove_item_btn.clicked.connect(self.remove_selected_item)
        
        controls_layout.addWidget(self.start_queue_btn)
        controls_layout.addWidget(self.pause_queue_btn)
        controls_layout.addWidget(self.remove_item_btn)
        
        layout.addWidget(self.queue_table)
        layout.addLayout(controls_layout)
        
        self.tabs.addTab(queue_tab, "Queue")
    
    def setup_history_tab(self):
        history_tab = QWidget()
        layout = QVBoxLayout(history_tab)
        
        # History table
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(["Title", "URL", "Format", "Date", "Status"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        
        # History controls
        controls_layout = QHBoxLayout()
        self.clear_history_btn = QPushButton("Clear History")
        self.clear_history_btn.clicked.connect(self.clear_history)
        
        self.redownload_btn = QPushButton("Re-download Selected")
        self.redownload_btn.clicked.connect(self.redownload_selected)
        
        controls_layout.addWidget(self.clear_history_btn)
        controls_layout.addWidget(self.redownload_btn)
        
        layout.addWidget(self.history_table)
        layout.addLayout(controls_layout)
        
        # Populate history table
        self.update_history_table()
        
        self.tabs.addTab(history_tab, "History")
    
    def setup_settings_tab(self):
        settings_tab = QWidget()
        layout = QVBoxLayout(settings_tab)
        
        # Default directory setting
        dir_layout = QHBoxLayout()
        dir_label = QLabel("Default Download Directory:")
        self.default_dir_input = QLineEdit()
        self.default_dir_input.setText(self.settings.value("default_directory", "", type=str))
        browse_default_btn = QPushButton("Browse")
        browse_default_btn.clicked.connect(self.browse_default_directory)
        
        dir_layout.addWidget(dir_label)
        dir_layout.addWidget(self.default_dir_input)
        dir_layout.addWidget(browse_default_btn)
        
        # Default format setting
        format_layout = QHBoxLayout()
        format_label = QLabel("Default Format:")
        self.default_format_combo = QComboBox()
        self.default_format_combo.addItems(["Video (MP4)", "Audio (MP3)"])
        default_format = self.settings.value("default_format", "Video (MP4)", type=str)
        default_index = 0 if default_format == "Video (MP4)" else 1
        self.default_format_combo.setCurrentIndex(default_index)
        
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.default_format_combo)
        
        # Theme setting
        theme_layout = QHBoxLayout()
        theme_label = QLabel("Theme:")
        self.theme_toggle = QCheckBox("Dark Mode")
        self.theme_toggle.setChecked(self.is_dark_mode)
        self.theme_toggle.stateChanged.connect(self.toggle_theme)
        
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.theme_toggle)
        
        # Save settings button
        self.save_settings_btn = QPushButton("Save Settings")
        self.save_settings_btn.clicked.connect(self.save_settings)
        
        # Add all layouts to main layout
        layout.addLayout(dir_layout)
        layout.addLayout(format_layout)
        layout.addLayout(theme_layout)
        layout.addWidget(self.save_settings_btn)
        layout.addStretch()
        
        self.tabs.addTab(settings_tab, "Settings")
    
    def browse_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Download Directory")
        if directory:
            self.dir_input.setText(directory)
    
    def browse_default_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Default Download Directory")
        if directory:
            self.default_dir_input.setText(directory)
    
    def update_quality_options(self):
        self.quality_combo.clear()
        if self.format_combo.currentText() == "Video (MP4)":
            self.quality_combo.addItems(["1080p", "720p", "480p", "360p"])
        else:  # Audio (MP3)
            self.quality_combo.addItems(["192 kbps", "128 kbps", "96 kbps"])
        
        # Set default quality from settings
        if self.format_combo.currentText() == "Video (MP4)":
            default_quality = self.settings.value("default_video_quality", "720p", type=str)
            index = self.quality_combo.findText(default_quality)
        else:
            default_quality = self.settings.value("default_audio_quality", "128 kbps", type=str)
            index = self.quality_combo.findText(default_quality)
        
        if index >= 0:
            self.quality_combo.setCurrentIndex(index)
    
    def add_to_queue(self):
        url = self.url_input.text().strip()
        output_path = self.dir_input.text().strip()
        format_type = self.format_combo.currentText()
        quality = self.quality_combo.currentText()
        
        if not url:
            self.show_error("Please enter a YouTube URL")
            return
        
        if not output_path:
            self.show_error("Please select a download directory")
            return
            
        # Check if output directory exists and is writable
        if not os.path.exists(output_path):
            try:
                os.makedirs(output_path, exist_ok=True)
                self.log_message(f"Created output directory: {output_path}")
            except Exception as e:
                self.show_error(f"Cannot create output directory: {str(e)}")
                return
        
        if not os.access(output_path, os.W_OK):
            self.show_error(f"No write permission for directory: {output_path}")
            return
        
        # Create download item
        download_item = DownloadItem(url, output_path, format_type, quality)
        
        # Add to queue
        self.download_queue.append(download_item)
        
        # Update queue display
        self.update_queue_table()
        
        # Clear URL input
        self.url_input.clear()
        
        # Show success message
        self.log_message(f"Added to queue: {url}")
        
        # Enable start button if it was disabled
        self.start_queue_btn.setEnabled(True)
        
        # Switch to queue tab
        self.tabs.setCurrentIndex(1)
    
    def update_queue_table(self):
        self.queue_table.setRowCount(len(self.download_queue))
        
        for i, item in enumerate(self.download_queue):
            # Title
            title_item = QTableWidgetItem(item.title)
            self.queue_table.setItem(i, 0, title_item)
            
            # URL
            url_item = QTableWidgetItem(item.url)
            self.queue_table.setItem(i, 1, url_item)
            
            # Format
            format_item = QTableWidgetItem(item.format_type)
            self.queue_table.setItem(i, 2, format_item)
            
            # Quality
            quality_item = QTableWidgetItem(item.quality)
            self.queue_table.setItem(i, 3, quality_item)
            
            # Progress
            progress_item = QTableWidgetItem(f"{item.progress}%")
            self.queue_table.setItem(i, 4, progress_item)
            
            # Status
            status_item = QTableWidgetItem(item.status)
            self.queue_table.setItem(i, 5, status_item)
    
    def start_queue(self):
        if not self.download_queue:
            self.show_error("Queue is empty")
            return
        
        if self.current_download is None and self.download_queue:
            self.process_next_in_queue()
            
            # Update button states
            self.start_queue_btn.setEnabled(False)
            self.pause_queue_btn.setEnabled(True)
    
    def process_next_in_queue(self):
        if not self.download_queue:
            self.current_download = None
            self.start_queue_btn.setEnabled(True)
            self.pause_queue_btn.setEnabled(False)
            return
        
        # Get next item in queue
        self.current_download = self.download_queue[0]
        self.current_download.status = "Downloading"
        self.update_queue_table()
        
        # Create worker thread
        self.current_download.worker = DownloadWorker(
            self.current_download.url,
            self.current_download.output_path,
            self.current_download.format_type,
            self.current_download.quality
        )
        
        # Connect signals
        self.current_download.worker.progress_signal.connect(self.update_progress)
        self.current_download.worker.finished_signal.connect(self.download_finished)
        self.current_download.worker.log_signal.connect(self.log_message)
        
        # Start worker
        self.current_download.worker.start()
    
    def update_progress(self, progress, status):
        if self.current_download:
            self.current_download.progress = progress
            self.progress_bar.setValue(progress)
            self.update_queue_table()
    
    def download_finished(self, url, success):
        if self.current_download:
            # Add to history
            history_item = {
                "url": self.current_download.url,
                "title": self.current_download.title if self.current_download.title != "Unknown" else url,
                "format": self.current_download.format_type,
                "quality": self.current_download.quality,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "Completed" if success else "Failed"
            }
            self.download_history.append(history_item)
            self.save_history()
            self.update_history_table()
            
            # Show notification
            if success:
                self.tray_icon.showMessage(
                    "Download Complete",
                    f"Successfully downloaded: {history_item['title']}",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000
                )
            else:
                self.tray_icon.showMessage(
                    "Download Failed",
                    f"Failed to download: {history_item['title']}",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000
                )
            
            # Remove from queue
            self.download_queue.pop(0)
            self.update_queue_table()
            
            # Reset progress bar
            self.progress_bar.setValue(0)
            
            # Process next item in queue
            self.current_download = None
            self.process_next_in_queue()
    
    def pause_queue(self):
        if self.current_download and self.current_download.worker:
            self.current_download.worker.cancel()
            self.current_download.status = "Paused"
            self.update_queue_table()
            
            # Update button states
            self.start_queue_btn.setEnabled(True)
            self.pause_queue_btn.setEnabled(False)
    
    def remove_selected_item(self):
        selected_rows = self.queue_table.selectedIndexes()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        
        # If removing current download
        if row == 0 and self.current_download:
            self.current_download.worker.cancel()
            self.current_download = None
        
        # Remove from queue
        if 0 <= row < len(self.download_queue):
            self.download_queue.pop(row)
            self.update_queue_table()
    
    def update_history_table(self):
        self.history_table.setRowCount(len(self.download_history))
        
        for i, item in enumerate(self.download_history):
            # Title
            title_item = QTableWidgetItem(item.get("title", "Unknown"))
            self.history_table.setItem(i, 0, title_item)
            
            # URL
            url_item = QTableWidgetItem(item.get("url", ""))
            self.history_table.setItem(i, 1, url_item)
            
            # Format
            format_item = QTableWidgetItem(item.get("format", ""))
            self.history_table.setItem(i, 2, format_item)
            
            # Date
            date_item = QTableWidgetItem(item.get("date", ""))
            self.history_table.setItem(i, 3, date_item)
            
            # Status
            status_item = QTableWidgetItem(item.get("status", ""))
            self.history_table.setItem(i, 4, status_item)
    
    def clear_history(self):
        reply = QMessageBox.question(
            self, 
            "Clear History", 
            "Are you sure you want to clear download history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.download_history = []
            self.save_history()
            self.update_history_table()
    
    def redownload_selected(self):
        selected_rows = self.history_table.selectedIndexes()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        
        if 0 <= row < len(self.download_history):
            item = self.download_history[row]
            
            # Add to queue
            download_item = DownloadItem(
                item.get("url", ""),
                self.settings.value("default_directory", "", type=str),
                item.get("format", "Video (MP4)"),
                item.get("quality", "720p")
            )
            download_item.title = item.get("title", "Unknown")
            
            self.download_queue.append(download_item)
            self.update_queue_table()
            
            # Switch to queue tab
            self.tabs.setCurrentIndex(1)
    
    def save_settings(self):
        # Save default directory
        self.settings.setValue("default_directory", self.default_dir_input.text())
        
        # Save default format
        self.settings.setValue("default_format", self.default_format_combo.currentText())
        
        # Save default qualities
        if self.quality_combo.count() > 0:
            if self.format_combo.currentText() == "Video (MP4)":
                self.settings.setValue("default_video_quality", self.quality_combo.currentText())
            else:
                self.settings.setValue("default_audio_quality", self.quality_combo.currentText())
        
        # Update UI with new settings
        self.dir_input.setText(self.default_dir_input.text())
        
        # Show confirmation
        QMessageBox.information(self, "Settings Saved", "Your settings have been saved successfully.")
    
    def toggle_theme(self, state):
        self.is_dark_mode = state == Qt.CheckState.Checked
        self.settings.setValue("dark_mode", self.is_dark_mode)
        self.apply_theme()
    
    def apply_theme(self):
        if self.is_dark_mode:
            # Dark theme
            self.setStyleSheet("""
                QWidget {
                    background-color: #2D2D2D;
                    color: #FFFFFF;
                    font-family: 'Segoe UI';
                    font-size: 12pt;
                }
                QPushButton {
                    background-color: #0D7377;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                }
                
                QPushButton:hover {
                    background-color: #14FFEC;
                    color: #2D2D2D;
                }
                QLineEdit, QTextEdit, QComboBox {
                    background-color: #3D3D3D;
                    color: #FFFFFF;
                    border: 1px solid #555555;
                    padding: 4px;
                    border-radius: 4px;
                }
                QTableWidget {
                    background-color: #3D3D3D;
                    color: #FFFFFF;
                    gridline-color: #555555;
                    border: 1px solid #555555;
                }
                QTableWidget::item:selected {
                    background-color: #0D7377;
                }
                QHeaderView::section {
                    background-color: #2D2D2D;
                    color: #FFFFFF;
                    border: 1px solid #555555;
                }
                QProgressBar {
                    border: 1px solid #555555;
                    border-radius: 4px;
                    text-align: center;
                    background-color: #3D3D3D;
                }
                QProgressBar::chunk {
                    background-color: #14FFEC;
                }
                QTabWidget::pane {
                    border: 1px solid #555555;
                }
                QTabBar::tab {
                    background-color: #2D2D2D;
                    color: #FFFFFF;
                    padding: 8px 16px;
                    border: 1px solid #555555;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #3D3D3D;
                }
            """)
        else:
            # Light theme
            self.setStyleSheet("""
                QWidget {
                    background-color: #FFFFFF;
                    color: #333333;
                    font-family: 'Segoe UI';
                    font-size: 12pt;
                }
                QPushButton {
                    background-color: #4F98CA;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #3A7CA5;
                }
                QLineEdit, QTextEdit, QComboBox {
                    background-color: #F5F5F5;
                    color: #333333;
                    border: 1px solid #DDDDDD;
                    padding: 4px;
                    border-radius: 4px;
                }
                QTableWidget {
                    background-color: #FFFFFF;
                    color: #333333;
                    gridline-color: #DDDDDD;
                    border: 1px solid #DDDDDD;
                }
                QTableWidget::item:selected {
                    background-color: #4F98CA;
                    color: #FFFFFF;
                }
                QHeaderView::section {
                    background-color: #F0F0F0;
                    color: #333333;
                    border: 1px solid #DDDDDD;
                }
                QProgressBar {
                    border: 1px solid #DDDDDD;
                    border-radius: 4px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #4F98CA;
                }
                QTabWidget::pane {
                    border: 1px solid #DDDDDD;
                }
                QTabBar::tab {
                    background-color: #F0F0F0;
                    color: #333333;
                    padding: 8px 16px;
                    border: 1px solid #DDDDDD;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #FFFFFF;
                }
            """)
    

    def load_history(self):
        try:
            history_file = os.path.join(os.path.expanduser("~"), "yt_downloader_history.json")
            if os.path.exists(history_file):
                with open(history_file, "r") as f:
                    self.download_history = json.load(f)
        except Exception as e:
            self.log_message(f"Error loading history: {str(e)}")
    
    def save_history(self):
        try:
            history_file = os.path.join(os.path.expanduser("~"), "yt_downloader_history.json")
            with open(history_file, "w") as f:
                json.dump(self.download_history, f)
        except Exception as e:
            self.log_message(f"Error saving history: {str(e)}")
    
    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        
        # Also log to file for debugging
        try:
            log_dir = os.path.join(os.path.expanduser("~"), "yt_downloader_logs")
            os.makedirs(log_dir, exist_ok=True)
            
            log_file = os.path.join(log_dir, f"log_{datetime.now().strftime('%Y%m%d')}.txt")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            print(f"Error writing to log file: {str(e)}")
    
    
    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().text()
        # Handle multiple URLs (one per line)
        for url in urls.split("\n"):
            url = url.strip()
            if url and ("youtube.com" in url or "youtu.be" in url):
                self.url_input.setText(url)
                break
    
    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, 
            "Exit", 
            "Are you sure you want to exit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

# Main application entry point
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = YTDownloaderGUI()
    sys.exit(app.exec())