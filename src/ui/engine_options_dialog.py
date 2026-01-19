"""
UCI Engine Options Dialog
Dynamically generates UI for configuring UCI engine options
"""

from typing import Dict, Any, Optional, Callable
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QSpinBox, QCheckBox, QComboBox,
    QPushButton, QScrollArea, QWidget, QGroupBox,
    QTabWidget, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal

from engine import UCIOption, UCIOptionType


class OptionWidget(QWidget):
    """Base widget for a single UCI option"""
    
    value_changed = pyqtSignal(str, object)  # option_name, value
    
    def __init__(self, option: UCIOption, current_value: Any = None, parent=None):
        super().__init__(parent)
        self.option = option
        self._setup_ui(current_value)
    
    def _setup_ui(self, current_value: Any):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        
        # Label
        label = QLabel(self.option.name)
        label.setMinimumWidth(150)
        label.setToolTip(self._get_tooltip())
        layout.addWidget(label)
        
        # Value widget based on type
        self.value_widget = self._create_value_widget(current_value)
        layout.addWidget(self.value_widget, stretch=1)
        
        # Reset button
        reset_btn = QPushButton("↺")
        reset_btn.setFixedWidth(30)
        reset_btn.setToolTip("Reset to default")
        reset_btn.clicked.connect(self._reset_to_default)
        layout.addWidget(reset_btn)
    
    def _get_tooltip(self) -> str:
        """Generate tooltip text for the option"""
        parts = [f"Type: {self.option.type.value}"]
        if self.option.default is not None:
            parts.append(f"Default: {self.option.default}")
        if self.option.min_val is not None:
            parts.append(f"Min: {self.option.min_val}")
        if self.option.max_val is not None:
            parts.append(f"Max: {self.option.max_val}")
        return "\n".join(parts)
    
    def _create_value_widget(self, current_value: Any) -> QWidget:
        """Create appropriate widget based on option type"""
        if self.option.type == UCIOptionType.SPIN:
            widget = QSpinBox()
            widget.setMinimum(self.option.min_val or 0)
            widget.setMaximum(self.option.max_val or 999999999)
            
            # Set current or default value
            if current_value is not None:
                try:
                    widget.setValue(int(current_value))
                except (ValueError, TypeError):
                    widget.setValue(self.option.default or 0)
            elif self.option.default is not None:
                widget.setValue(self.option.default)
            
            widget.valueChanged.connect(lambda v: self.value_changed.emit(self.option.name, v))
            return widget
        
        elif self.option.type == UCIOptionType.CHECK:
            widget = QCheckBox()
            
            if current_value is not None:
                widget.setChecked(str(current_value).lower() in ('true', '1', 'yes'))
            elif self.option.default is not None:
                widget.setChecked(bool(self.option.default))
            
            widget.stateChanged.connect(lambda: self.value_changed.emit(self.option.name, widget.isChecked()))
            return widget
        
        elif self.option.type == UCIOptionType.COMBO:
            widget = QComboBox()
            if self.option.var_list:
                widget.addItems(self.option.var_list)
                
                if current_value is not None and current_value in self.option.var_list:
                    widget.setCurrentText(str(current_value))
                elif self.option.default and self.option.default in self.option.var_list:
                    widget.setCurrentText(self.option.default)
            
            widget.currentTextChanged.connect(lambda v: self.value_changed.emit(self.option.name, v))
            return widget
        
        elif self.option.type == UCIOptionType.STRING:
            widget = QLineEdit()
            
            if current_value is not None:
                widget.setText(str(current_value))
            elif self.option.default:
                widget.setText(self.option.default)
            
            widget.textChanged.connect(lambda v: self.value_changed.emit(self.option.name, v))
            return widget
        
        elif self.option.type == UCIOptionType.BUTTON:
            widget = QPushButton("Trigger")
            widget.clicked.connect(lambda: self.value_changed.emit(self.option.name, None))
            return widget
        
        else:
            # Fallback to line edit
            widget = QLineEdit()
            widget.textChanged.connect(lambda v: self.value_changed.emit(self.option.name, v))
            return widget
    
    def _reset_to_default(self):
        """Reset value to default"""
        if self.option.type == UCIOptionType.SPIN:
            self.value_widget.setValue(self.option.default or 0)
        elif self.option.type == UCIOptionType.CHECK:
            self.value_widget.setChecked(bool(self.option.default))
        elif self.option.type == UCIOptionType.COMBO:
            if self.option.default:
                self.value_widget.setCurrentText(self.option.default)
        elif self.option.type == UCIOptionType.STRING:
            self.value_widget.setText(self.option.default or "")
    
    def get_value(self) -> Any:
        """Get current value"""
        if self.option.type == UCIOptionType.SPIN:
            return self.value_widget.value()
        elif self.option.type == UCIOptionType.CHECK:
            return self.value_widget.isChecked()
        elif self.option.type == UCIOptionType.COMBO:
            return self.value_widget.currentText()
        elif self.option.type == UCIOptionType.STRING:
            return self.value_widget.text()
        elif self.option.type == UCIOptionType.BUTTON:
            return None
        return None


class EngineOptionsDialog(QDialog):
    """Dialog for configuring UCI engine options"""
    
    options_changed = pyqtSignal(dict)  # Emitted when options are saved
    
    def __init__(self, engine_name: str, 
                 options: Dict[str, UCIOption],
                 current_values: Dict[str, str] = None,
                 parent=None):
        super().__init__(parent)
        
        self.engine_name = engine_name
        self.available_options = options
        self.current_values = current_values or {}
        self.modified_values: Dict[str, Any] = {}
        self.option_widgets: Dict[str, OptionWidget] = {}
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the dialog UI"""
        self.setWindowTitle(f"Engine Options - {self.engine_name}")
        self.setMinimumSize(500, 400)
        self.resize(600, 500)
        
        layout = QVBoxLayout(self)
        
        # Info label
        info_label = QLabel(f"Configure UCI options for {self.engine_name}")
        info_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        # Tab widget for organized options
        tabs = QTabWidget()
        layout.addWidget(tabs, stretch=1)
        
        # Categorize options
        common_options = {}
        performance_options = {}
        other_options = {}
        
        common_names = ["UCI_LimitStrength", "UCI_Elo", "Skill Level", "MultiPV"]
        performance_names = ["Threads", "Hash", "SyzygyPath", "SyzygyProbeLimit", "Ponder"]
        
        for name, opt in self.available_options.items():
            if name in common_names:
                common_options[name] = opt
            elif name in performance_names:
                performance_options[name] = opt
            else:
                other_options[name] = opt
        
        # Create tabs
        if common_options:
            tabs.addTab(self._create_options_tab(common_options), "Strength & Style")
        if performance_options:
            tabs.addTab(self._create_options_tab(performance_options), "Performance")
        if other_options:
            tabs.addTab(self._create_options_tab(other_options), "All Options")
        
        # Buttons
        button_layout = QHBoxLayout()
        
        reset_all_btn = QPushButton("Reset All to Defaults")
        reset_all_btn.clicked.connect(self._reset_all)
        button_layout.addWidget(reset_all_btn)
        
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_and_close)
        button_layout.addWidget(save_btn)
        
        layout.addLayout(button_layout)
    
    def _create_options_tab(self, options: Dict[str, UCIOption]) -> QWidget:
        """Create a scrollable tab with option widgets"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(5)
        
        for name, opt in sorted(options.items()):
            # Skip button type options in the main list (they're actions)
            if opt.type == UCIOptionType.BUTTON:
                continue
            
            current_val = self.current_values.get(name)
            widget = OptionWidget(opt, current_val, container)
            widget.value_changed.connect(self._on_value_changed)
            
            self.option_widgets[name] = widget
            layout.addWidget(widget)
        
        layout.addStretch()
        scroll.setWidget(container)
        return scroll
    
    def _on_value_changed(self, name: str, value: Any):
        """Handle option value change"""
        self.modified_values[name] = value
    
    def _reset_all(self):
        """Reset all options to defaults"""
        reply = QMessageBox.question(
            self, "Reset All",
            "Reset all options to their default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            for widget in self.option_widgets.values():
                widget._reset_to_default()
    
    def _save_and_close(self):
        """Save options and close dialog"""
        # Collect all current values
        result = {}
        for name, widget in self.option_widgets.items():
            value = widget.get_value()
            if value is not None:
                result[name] = value
        
        self.options_changed.emit(result)
        self.accept()
    
    def get_options(self) -> Dict[str, Any]:
        """Get all option values"""
        result = {}
        for name, widget in self.option_widgets.items():
            value = widget.get_value()
            if value is not None:
                result[name] = value
        return result


def create_quick_strength_dialog(engine_name: str,
                                  options: Dict[str, UCIOption],
                                  current_values: Dict[str, str] = None,
                                  parent=None) -> Optional[Dict[str, Any]]:
    """
    Create a simplified dialog for just strength settings
    Returns the selected options or None if cancelled
    """
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"Engine Strength - {engine_name}")
    dialog.setMinimumWidth(350)
    
    layout = QVBoxLayout(dialog)
    
    result = {}
    
    # Check if engine supports strength limiting
    has_limit_strength = "UCI_LimitStrength" in options
    has_elo = "UCI_Elo" in options
    has_skill = "Skill Level" in options
    
    if not (has_limit_strength or has_elo or has_skill):
        # Engine doesn't support strength limiting
        label = QLabel("This engine does not support strength limiting.\n\n"
                      "It will play at full strength.")
        label.setWordWrap(True)
        layout.addWidget(label)
        
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        layout.addWidget(ok_btn)
        
        dialog.exec()
        return {}
    
    # Strength limiting checkbox
    if has_limit_strength:
        limit_cb = QCheckBox("Limit Engine Strength")
        current = current_values.get("UCI_LimitStrength", "false") if current_values else "false"
        limit_cb.setChecked(current.lower() == "true")
        layout.addWidget(limit_cb)
    
    # ELO slider
    if has_elo:
        elo_opt = options["UCI_Elo"]
        elo_group = QGroupBox("Target ELO")
        elo_layout = QHBoxLayout(elo_group)
        
        elo_spin = QSpinBox()
        elo_spin.setMinimum(elo_opt.min_val or 800)
        elo_spin.setMaximum(elo_opt.max_val or 3200)
        
        current = current_values.get("UCI_Elo") if current_values else None
        if current:
            try:
                elo_spin.setValue(int(current))
            except ValueError:
                elo_spin.setValue(elo_opt.default or 1500)
        else:
            elo_spin.setValue(elo_opt.default or 1500)
        
        elo_layout.addWidget(QLabel("ELO:"))
        elo_layout.addWidget(elo_spin, stretch=1)
        layout.addWidget(elo_group)
    
    # Skill level slider
    if has_skill:
        skill_opt = options["Skill Level"]
        skill_group = QGroupBox("Skill Level")
        skill_layout = QHBoxLayout(skill_group)
        
        skill_spin = QSpinBox()
        skill_spin.setMinimum(skill_opt.min_val or 0)
        skill_spin.setMaximum(skill_opt.max_val or 20)
        
        current = current_values.get("Skill Level") if current_values else None
        if current:
            try:
                skill_spin.setValue(int(current))
            except ValueError:
                skill_spin.setValue(skill_opt.default or 20)
        else:
            skill_spin.setValue(skill_opt.default or 20)
        
        skill_layout.addWidget(QLabel("Level:"))
        skill_layout.addWidget(skill_spin, stretch=1)
        skill_layout.addWidget(QLabel(f"(0=weakest, {skill_opt.max_val or 20}=strongest)"))
        layout.addWidget(skill_group)
    
    # Buttons
    btn_layout = QHBoxLayout()
    cancel_btn = QPushButton("Cancel")
    cancel_btn.clicked.connect(dialog.reject)
    btn_layout.addWidget(cancel_btn)
    
    ok_btn = QPushButton("Apply")
    ok_btn.setDefault(True)
    
    def on_apply():
        if has_limit_strength:
            result["UCI_LimitStrength"] = limit_cb.isChecked()
        if has_elo:
            result["UCI_Elo"] = elo_spin.value()
        if has_skill:
            result["Skill Level"] = skill_spin.value()
        dialog.accept()
    
    ok_btn.clicked.connect(on_apply)
    btn_layout.addWidget(ok_btn)
    
    layout.addLayout(btn_layout)
    
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return result
    return None
