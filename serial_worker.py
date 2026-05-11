import serial
import numpy as np
from PySide6.QtCore import QThread, Signal
import time


class SerialWorker(QThread):
    # Sends arrays of shape (N, 8) where N is number of samples
    # Variables: M_SIN, M_COS, N_SIN, N_COS, S_SIN, S_COS, MTAB, HALL
    data_received = Signal(np.ndarray)
    error_occurred = Signal(str)
    connection_status = Signal(bool)

    def __init__(self, port, baudrate=2500000):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.running = False
        self.ser = None

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
            self.connection_status.emit(True)
        except Exception as e:
            self.error_occurred.emit(str(e))
            self.connection_status.emit(False)
            return

        self.running = True
        buffer = bytearray()

        # Pre-allocate numpy arrays to avoid constant allocation
        batch_size = 500
        data_batch = np.zeros((batch_size, 26), dtype=np.float32)
        batch_idx = 0

        while self.running:
            try:
                # Read as much as available, or block until timeout
                raw = self.ser.read(self.ser.in_waiting or 4096)
                if not raw:
                    continue
                buffer.extend(raw)

                # Parse frames
                i = 0
                while i <= len(buffer) - 12:
                    if buffer[i] == 0x85:
                        frame = buffer[i:i + 12]

                        # Verify checksum
                        checksum = 0
                        for j in range(11):
                            checksum ^= frame[j]

                        if checksum == frame[11]:
                            # Valid frame
                            m_sin = frame[1] | ((frame[7] >> 4) << 8)
                            m_cos = frame[2] | ((frame[7] & 0x0F) << 8)
                            n_sin = frame[3] | ((frame[8] >> 4) << 8)
                            n_cos = frame[4] | ((frame[8] & 0x0F) << 8)
                            s_sin = frame[5] | ((frame[9] >> 4) << 8)
                            s_cos = frame[6] | ((frame[9] & 0x0F) << 8)
                            hall = (frame[10] & 0x30) >> 4
                            mtab = frame[10] & 0x03

                            data_batch[batch_idx, 0] = m_sin
                            data_batch[batch_idx, 1] = m_cos
                            data_batch[batch_idx, 2] = n_sin
                            data_batch[batch_idx, 3] = n_cos
                            data_batch[batch_idx, 4] = s_sin
                            data_batch[batch_idx, 5] = s_cos
                            data_batch[batch_idx, 6] = mtab
                            data_batch[batch_idx, 7] = hall

                            batch_idx += 1
                            if batch_idx >= batch_size:
                                # Compute block-wise max, min, offset for M_SIN, M_COS, N_SIN, N_COS, S_SIN, S_COS
                                for ch in range(6):
                                    b_max = np.max(data_batch[:, ch])
                                    b_min = np.min(data_batch[:, ch])
                                    b_ofs = (b_max + b_min) / 2.0
                                    
                                    data_batch[:, 8 + ch*3] = b_max
                                    data_batch[:, 8 + ch*3 + 1] = b_min
                                    data_batch[:, 8 + ch*3 + 2] = b_ofs
                                    
                                self.data_received.emit(data_batch.copy())
                                batch_idx = 0

                            i += 12
                        else:
                            # Bad checksum, advance by 1
                            i += 1
                    else:
                        i += 1

                # Keep remaining bytes
                del buffer[:i]

            except serial.SerialException as e:
                self.error_occurred.emit(str(e))
                break

        if self.ser and self.ser.is_open:
            self.ser.close()
        self.connection_status.emit(False)

    def send_data(self, data: bytes):
        if self.ser and self.ser.is_open:
            self.ser.write(data)

    def stop(self):
        self.running = False
        self.wait()
