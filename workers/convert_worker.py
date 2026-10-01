from PyQt5 import QtCore


class ConvertFileWorker(QtCore.QThread):
    status_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(str)

    def __init__(self, input_path, output_type="MP3", target_resolution=None,
                 target_format=None, copy_streams=None):
        super().__init__()
        self.input_path = input_path
        self.output_type = output_type
        self.target_resolution = target_resolution
        self.target_format = target_format
        self.copy_streams = copy_streams

    def run(self):
        from core.convert import convert_file

        self.status_signal.emit("Converting...")
        result = convert_file(
            self.input_path, self.output_type, self.target_resolution,
            self.target_format, self.copy_streams,
        )
        self.finished_signal.emit(result.message or result.path or result.status)
