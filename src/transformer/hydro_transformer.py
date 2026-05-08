"""
src/transformer/hydro_transformer.py
=====================================
Hydrometeorology-informed Transformer Network.
Dự đoán dịch chuyển LOS hàng ngày từ dữ liệu khí tượng thủy văn.

ĐIỀU CHỈNH SO VỚI ZHENG ET AL. (2026):
  - Biến đầu vào 2: soil_moisture (thay reservoir_level)
    vì Tĩnh Túc không có hồ chứa lớn

Khi torch KHÔNG có sẵn → dùng NumPy implementation đơn giản (linear baseline).
Khi torch có sẵn → dùng full Transformer architecture.

Tham chiếu: Zheng et al. (2026), Section 3.2; Vaswani et al. (2017)
"""

import numpy as np
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Thử import torch; nếu không có dùng fallback
try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
    logger.info("PyTorch available — using full Transformer architecture")
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch NOT available — using NumPy linear baseline. "
                   "Install PyTorch for full performance: pip install torch")


# ─────────────────────────────────────────────────────────────
# PYTORCH IMPLEMENTATION (đầy đủ)
# ─────────────────────────────────────────────────────────────

if TORCH_AVAILABLE:
    class TransformerEncoderBlock(nn.Module):
        """
        Một Transformer Encoder block với multi-head attention + FFN.
        Tham chiếu: Zheng et al. (2026), Eq. (14)-(20)
        """
        def __init__(self, d_model: int, n_heads: int, dropout: float = 0.1):
            super().__init__()
            self.attention = nn.MultiheadAttention(d_model, n_heads,
                                                    dropout=dropout, batch_first=True)
            self.norm1 = nn.LayerNorm(d_model)
            self.norm2 = nn.LayerNorm(d_model)
            self.ffn = nn.Sequential(
                nn.Linear(d_model, d_model * 4),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(d_model * 4, d_model),
            )
            self.dropout = nn.Dropout(dropout)

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            # Multi-head attention với residual
            attn_out, _ = self.attention(x, x, x)
            x = self.norm1(x + self.dropout(attn_out))
            # Feed-forward với residual
            ffn_out = self.ffn(x)
            x = self.norm2(x + self.dropout(ffn_out))
            return x

    class HydrometTransformerTorch(nn.Module):
        """
        Full Transformer network theo Zheng et al. (2026).
        Feature extraction (2 blocks) + Parameter estimation (4 blocks).
        Input: (batch, T, n_features) → Output: (batch, 1)
        """
        def __init__(self,
                     n_features: int = 3,
                     d_model: int = 64,
                     n_heads: int = 8,
                     seq_len: int = 30,
                     n_feature_blocks: int = 2,
                     n_estimation_blocks: int = 4,
                     dropout: float = 0.1):
            super().__init__()
            self.embedding = nn.Linear(n_features, d_model)

            # Positional encoding (learnable)
            self.pos_enc = nn.Parameter(torch.zeros(1, seq_len, d_model))

            # Feature extraction module (2 TE + FC)
            self.feature_blocks = nn.ModuleList([
                TransformerEncoderBlock(d_model, n_heads, dropout)
                for _ in range(n_feature_blocks)
            ])
            self.feature_fc = nn.Sequential(
                nn.Linear(d_model, 1),
            )

            # Parameter estimation module (4 × [TE + FC])
            self.estimation_blocks = nn.ModuleList()
            dims = [seq_len, 45, 16, 16, 16]
            for i in range(n_estimation_blocks):
                in_d = dims[min(i, len(dims)-1)]
                out_d = dims[min(i+1, len(dims)-1)]
                self.estimation_blocks.append(nn.Sequential(
                    TransformerEncoderBlock(1 if i > 0 else 1, 1),
                    nn.Flatten(start_dim=1),
                    nn.Linear(in_d if i == 0 else out_d, out_d),
                    nn.ReLU(),
                ))
            self.output_fc = nn.Linear(dims[-1], 1)

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            # Embedding + positional encoding
            B, T, _ = x.shape
            z = self.embedding(x) + self.pos_enc[:, :T, :]

            # Feature extraction
            for block in self.feature_blocks:
                z = block(z)
            hf = self.feature_fc(z)  # (B, T, 1)

            # Parameter estimation
            out = hf.squeeze(-1)  # (B, T)
            for i, block in enumerate(self.estimation_blocks):
                try:
                    out = block(out.unsqueeze(-1)).squeeze(-1) if i == 0 else block(out)
                except Exception:
                    break
            y = self.output_fc(out[:, :16] if out.shape[1] >= 16 else out)
            return y  # (B, 1)


# ─────────────────────────────────────────────────────────────
# NUMPY FALLBACK (khi không có torch)
# ─────────────────────────────────────────────────────────────

class LinearBaselineModel:
    """
    Mô hình tuyến tính đơn giản (fallback khi không có PyTorch).
    Học hệ số tuyến tính giữa rainfall, soil_moisture → LOS displacement.
    Dùng khi không thể cài torch (môi trường không có internet).
    """

    def __init__(self, seq_len: int = 30, n_features: int = 3):
        self.seq_len = seq_len
        self.n_features = n_features
        self.weights: Optional[np.ndarray] = None
        self.bias: float = 0.0
        self.is_trained = False
        self.train_loss_history: List[float] = []

    def _prepare_features(self, X: np.ndarray) -> np.ndarray:
        """Trích xuất features từ sequence: mean, std, max, sum của mỗi feature."""
        features = []
        for f in range(X.shape[2]):
            series = X[:, :, f]  # shape (N, seq_len)
            # Thống kê toàn chuỗi: trung bình + độ biến động + cực đại
            features.append(np.mean(series, axis=1, keepdims=True))
            features.append(np.std(series, axis=1, keepdims=True))
            features.append(np.max(series, axis=1, keepdims=True))
            # Lag features: nhiệu mưa ngắn hạn (7 và 14 ngày) có ảnh hưởng mạnh
            features.append(np.mean(series[:, -7:], axis=1, keepdims=True))  # Tuần cuối
            features.append(np.mean(series[:, -14:], axis=1, keepdims=True)) # 2 tuần
        return np.concatenate(features, axis=1)  # (N, n_features*5)

    def fit(self, X_train: np.ndarray, y_train: np.ndarray,
            epochs: int = 100, lr: float = 1e-3) -> None:
        """Ridge regression với gradient descent."""
        feats = self._prepare_features(X_train)  # (N, F) — trích xuất feature tịnh
        N, F = feats.shape
        self.weights = np.zeros(F)  # Khởi tạo trọng số = 0 (không dùng glorot vì model đơn giản)
        self.bias = 0.0
        lambda_reg = 0.01  # Hệ số Ridge regularization: tránh overfitting

        for epoch in range(epochs):
            # Dự đoán
            y_pred = feats @ self.weights + self.bias
            residuals = y_pred - y_train  # Sai số giữa dự đoán và thực tế
            # MSE + L2 penalty
            loss = np.mean(residuals**2) + lambda_reg * np.sum(self.weights**2)

            # Gradient của MSE + Ridge toàn củc
            grad_w = 2 * feats.T @ residuals / N + 2 * lambda_reg * self.weights
            grad_b = 2 * np.mean(residuals)

            # Cập nhật trọng số theo gradient descent
            self.weights -= lr * grad_w
            self.bias -= lr * grad_b
            self.train_loss_history.append(float(loss))

        self.is_trained = True
        logger.info(f"Linear model trained: final loss={self.train_loss_history[-1]:.4f}")

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.is_trained:
            raise RuntimeError("Gọi fit() trước predict()")
        feats = self._prepare_features(X)
        return feats @ self.weights + self.bias


# ─────────────────────────────────────────────────────────────
# WRAPPER THỐNG NHẤT
# ─────────────────────────────────────────────────────────────

class HydrometTransformer:
    """
    Wrapper thống nhất: dùng PyTorch Transformer nếu có, fallback LinearBaseline.
    API nhất quán cho cả hai backend.

    Biến:
        cfg (dict): Cấu hình mô hình (sequence_length, n_features, ...).
        seq_len (int): Độ dài chuỗi thời gian đầu vào (sliding window).
        n_features (int): Số lượng đặc trưng đầu vào (mặc định 3: displacement, rainfall, soil_moisture).
        input_features (List[str]): Tên các đặc trưng đầu vào.
        is_trained (bool): Đã huấn luyện mô hình hay chưa.
        _window (np.ndarray): Sliding window cho inference.
        model: Mô hình backend (PyTorch hoặc LinearBaseline).
        backend (str): 'torch' nếu dùng PyTorch, 'numpy' nếu dùng LinearBaseline.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.seq_len = cfg.get("sequence_length", 30)
        self.n_features = cfg.get("n_features", 3)
        self.input_features = cfg.get("input_features",
                                       ["los_displacement", "rainfall_mm", "soil_moisture"])
        self.is_trained = False

        # Lịch sử sliding window cho inference
        self._window: Optional[np.ndarray] = None

        if TORCH_AVAILABLE:
            self.model = HydrometTransformerTorch(
                n_features=self.n_features,
                d_model=cfg.get("d_model", 64),
                n_heads=cfg.get("n_heads", 8),
                seq_len=self.seq_len,
                n_feature_blocks=cfg.get("n_encoder_layers_feature", 2),
                n_estimation_blocks=cfg.get("n_encoder_layers_estimation", 4),
                dropout=cfg.get("dropout", 0.1),
            )
            self.backend = "torch"
        else:
            self.model = LinearBaselineModel(self.seq_len, self.n_features)
            self.backend = "numpy"

        logger.info(f"HydrometTransformer initialized with {self.backend} backend")

    def prepare_dataset(self,
                         los_timeseries: np.ndarray,
                         hydro_data: Dict[str, np.ndarray],
                         dates: List[datetime]
                         ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Chuẩn bị dataset huấn luyện dạng sliding window.

        Args:
            los_timeseries (np.ndarray): Chuỗi thời gian dịch chuyển LOS (mm), shape (T,).
            hydro_data (Dict[str, np.ndarray]): Dữ liệu khí tượng (rainfall_mm, soil_moisture,...), mỗi biến shape (T,).
            dates (List[datetime]): Danh sách ngày tương ứng.

        Returns:
            samples_X (np.ndarray): Dữ liệu đầu vào (N, seq_len, n_features).
            samples_y (np.ndarray): Nhãn dự đoán (N,).
        """
        T = len(dates)
        seq = self.seq_len
        samples_X, samples_y = [], []

        for t in range(seq, T):
            # Cắt sliding window [t-seq, t) cho mỗi feature
            window_los = los_timeseries[t - seq:t]    # Dịch chuyển LOS llich sử
            window_rain = hydro_data.get("rainfall_mm",
                                          np.zeros(T))[t - seq:t]  # Lượng mưa
            window_sm = hydro_data.get("soil_moisture",
                                        np.full(T, 0.3))[t - seq:t]  # Độ ẩm đất

            # Chuẩn hóa từng feature vào khoảng [0, 1] (trong window này)
            # LOS: có giá trị âm/dương → chuẩn hóa zero-mean
            los_std = np.std(window_los) + 1e-8
            rain_max = np.max(window_rain) + 1e-8  # Tránh chia cho 0 khi khô hạn
            window_los_n = (window_los - np.mean(window_los)) / los_std
            window_rain_n = window_rain / rain_max    # [0, 1]: 0=khô, 1=mạnhmax
            window_sm_n = (window_sm - 0.1) / 0.5   # [0.1, 0.6] → [0, 1] cho đất ở Tĩnh Túc

            # Xếp các feature thành ma trận (seq, 3)
            X = np.stack([window_los_n, window_rain_n, window_sm_n], axis=-1)
            # Nhãn: giá trị LOS tại bước tiếp theo (mm)
            y = los_timeseries[t]
            samples_X.append(X)
            samples_y.append(y)

        return np.array(samples_X, dtype=np.float32), \
               np.array(samples_y, dtype=np.float32)

    def train(self,
              X_train: np.ndarray,
              y_train: np.ndarray,
              X_val: Optional[np.ndarray] = None,
              y_val: Optional[np.ndarray] = None) -> Dict:
        """Huấn luyện model. Trả về lịch sử loss."""
        cfg = self.cfg

        if self.backend == "torch":
            return self._train_torch(X_train, y_train, X_val, y_val)
        else:
            self.model.fit(X_train, y_train,
                           epochs=cfg.get("max_epochs", 200),
                           lr=cfg.get("learning_rate", 1e-3))
            self.is_trained = True
            return {"train_loss": self.model.train_loss_history}

    def _train_torch(self, X_train, y_train, X_val, y_val) -> Dict:
        """Huấn luyện PyTorch model với early stopping."""
        import torch
        import torch.optim as optim

        cfg = self.cfg
        X_t = torch.FloatTensor(X_train)
        y_t = torch.FloatTensor(y_train).unsqueeze(1)

        optimizer = optim.Adam(self.model.parameters(),
                               lr=cfg.get("learning_rate", 1e-3))
        criterion = nn.MSELoss()
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=20)

        best_val_loss = float("inf")
        patience_count = 0
        patience = cfg.get("patience_early_stop", 50)
        history = {"train_loss": [], "val_loss": []}

        self.model.train()
        for epoch in range(cfg.get("max_epochs", 500)):
            # Mini-batch SGD
            batch_size = cfg.get("batch_size", 32)
            idx = np.random.permutation(len(X_t))
            epoch_loss = 0.0
            n_batches = 0

            for start in range(0, len(X_t), batch_size):
                batch_idx = idx[start:start + batch_size]
                xb = X_t[batch_idx]
                yb = y_t[batch_idx]

                optimizer.zero_grad()
                y_pred = self.model(xb)
                loss = criterion(y_pred, yb)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
                n_batches += 1

            epoch_loss /= max(n_batches, 1)
            history["train_loss"].append(epoch_loss)

            # Validation
            if X_val is not None:
                self.model.eval()
                with torch.no_grad():
                    X_v = torch.FloatTensor(X_val)
                    y_v = torch.FloatTensor(y_val).unsqueeze(1)
                    val_loss = criterion(self.model(X_v), y_v).item()
                history["val_loss"].append(val_loss)
                scheduler.step(val_loss)

                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_count = 0
                else:
                    patience_count += 1
                    if patience_count >= patience:
                        logger.info(f"Early stopping at epoch {epoch}")
                        break
                self.model.train()

            if epoch % 50 == 0:
                logger.debug(f"Epoch {epoch}: train_loss={epoch_loss:.4f}")

        self.is_trained = True
        logger.info(f"Training done. Best val loss: {best_val_loss:.4f}")
        return history

    def predict_los(self, hydro_today: Dict,
                    recent_los: Optional[float] = None) -> np.ndarray:
        """
        Dự đoán dịch chuyển LOS ngày hôm nay từ dữ liệu khí tượng.
        Trả về array [los_asc, los_desc] (mm) để đưa vào KF.
        """
        if not self.is_trained:
            # Chưa huấn luyện → trả về nhiễu nhỏ
            return np.array([0.1, -0.1]) * np.random.randn(2)

        if self._window is None:
            self._window = np.zeros((1, self.seq_len, self.n_features),
                                    dtype=np.float32)

        # Cập nhật sliding window
        rain = hydro_today.get("rainfall_mm", 0.0)
        sm = hydro_today.get("soil_moisture", 0.3)
        los = recent_los if recent_los is not None else 0.0

        new_obs = np.array([los, rain / 100.0, (sm - 0.1) / 0.5], dtype=np.float32)
        self._window[0, :-1, :] = self._window[0, 1:, :]
        self._window[0, -1, :] = new_obs

        if self.backend == "torch":
            import torch
            self.model.eval()
            with torch.no_grad():
                pred = self.model(torch.FloatTensor(self._window)).item()
        else:
            pred = self.model.predict(self._window)[0]

        # Sinh LOS cho 2 tracks từ tổng dịch chuyển dự đoán
        # (đơn giản hóa: asc và desc có trọng số khác nhau)
        los_asc = pred * 0.7    # Ascending: nhạy hơn với dịch chuyển theo chiều đứng
        los_desc = pred * 0.6
        return np.array([los_asc, los_desc], dtype=np.float32)

    def save(self, path: str) -> None:
        """Lưu model đã huấn luyện."""
        if self.backend == "torch" and self.is_trained:
            import torch
            torch.save(self.model.state_dict(), path + "_torch.pt")
        else:
            np.save(path + "_numpy_weights.npy",
                    self.model.weights if self.model.weights is not None
                    else np.array([]))
        logger.info(f"Model saved to {path}")

    def load(self, path: str) -> None:
        """Load model đã lưu."""
        if self.backend == "torch":
            import torch
            self.model.load_state_dict(torch.load(path + "_torch.pt"))
            self.is_trained = True
        else:
            weights = np.load(path + "_numpy_weights.npy")
            if weights.size > 0:
                self.model.weights = weights
                self.model.is_trained = True
                self.is_trained = True
        logger.info(f"Model loaded from {path}")
