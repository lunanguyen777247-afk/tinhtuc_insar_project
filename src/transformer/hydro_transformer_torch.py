"""
src/transformer/hydro_transformer_torch.py
===========================================
PyTorch implementation of Hydromet Transformer for InSAR time series fusion.

Learns nonlinear relationships between hydrometeorological variables
(precipitation, soil moisture, groundwater level, temperature) and
InSAR deformation using multi-head self-attention.

Improves over LinearBaseline by:
- Capturing nonlinear hydro-deformation coupling
- Learning long-range temporal dependencies (30-90 day cycles)
- Automatic feature engineering via attention mechanism
- Improved generalization with proper train/val/test split
"""

import numpy as np
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

logger = logging.getLogger(__name__)


@dataclass
class TransformerConfig:
    """Configuration for PyTorch Transformer."""
    # Model architecture
    seq_length: int = 90  # Input sequence length (days)
    n_features: int = 5   # [d_kalman, P, SM, GWL, T]
    d_model: int = 32     # Embedding dimension
    n_heads: int = 4      # Number of attention heads
    n_layers: int = 2     # Number of encoder layers
    d_ff: int = 64        # Feed-forward dimension
    dropout: float = 0.1
    
    # Training
    batch_size: int = 32
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    n_epochs: int = 100
    early_stopping_patience: int = 10
    
    # Device
    device: str = "cuda" if torch.cuda.is_available() else "cpu"


class TimeSeriesDataset(Dataset):
    """Dataset for time series prediction."""
    
    def __init__(self,
                 data: np.ndarray,
                 seq_length: int,
                 train: bool = True,
                 train_ratio: float = 0.7):
        """
        Args:
            data: Shape (T, H, W, F) where F features
            seq_length: Sequence length for each sample
            train: Use training or validation split
            train_ratio: Fraction for training
        """
        T, H, W, F = data.shape
        
        # Flatten spatial dimensions
        data_flat = data.reshape(T, H*W, F)  # (T, H*W, F)
        
        # Create sequences
        self.sequences = []
        self.targets = []
        
        for i in range(T - seq_length):
            seq = data_flat[i:i+seq_length]  # (seq_len, H*W, F)
            tgt = data_flat[i+seq_length, :, 0]  # Next displacement (H*W,)
            
            self.sequences.append(seq)
            self.targets.append(tgt)
        
        self.sequences = np.array(self.sequences)  # (N_seq, seq_len, H*W, F)
        self.targets = np.array(self.targets)     # (N_seq, H*W)
        
        # Train/val split
        n_samples = len(self.sequences)
        n_train = int(n_samples * train_ratio)
        
        if train:
            self.sequences = self.sequences[:n_train]
            self.targets = self.targets[:n_train]
        else:
            self.sequences = self.sequences[n_train:]
            self.targets = self.targets[n_train:]
        
        self.n_pixels = H * W
    
    def __len__(self):
        return len(self.sequences)
    
    def __getitem__(self, idx):
        seq = torch.FloatTensor(self.sequences[idx])  # (seq_len, H*W, F)
        tgt = torch.FloatTensor(self.targets[idx])    # (H*W,)
        return seq, tgt


class TransformerEncoder(nn.Module):
    """Transformer encoder for sequence modeling."""
    
    def __init__(self, cfg: TransformerConfig):
        super().__init__()
        
        # Input embedding
        self.embedding = nn.Linear(cfg.n_features, cfg.d_model)
        
        # Positional encoding (learnable)
        self.pos_encoding = nn.Parameter(
            torch.randn(1, cfg.seq_length, cfg.d_model)
        )
        
        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=cfg.d_model,
            nhead=cfg.n_heads,
            dim_feedforward=cfg.d_ff,
            dropout=cfg.dropout,
            batch_first=True,
            activation='gelu'
        )
        self.transformer = nn.TransformerEncoder(
            encoder_layer,
            num_layers=cfg.n_layers
        )
        
        # Output layers
        self.dropout = nn.Dropout(cfg.dropout)
        self.fc_out = nn.Linear(cfg.d_model, 1)  # Predict displacement anomaly
    
    def forward(self, x):
        """
        Args:
            x: Shape (B, T, H*W, F) where B=batch, T=seq_len
        
        Returns:
            output: Shape (B, H*W, 1) predictions
        """
        B, T, n_pixels, F = x.shape
        
        # Reshape to (B*H*W, T, F) to process each pixel independently
        x = x.permute(0, 2, 1, 3)  # (B, H*W, T, F)
        x = x.reshape(B*n_pixels, T, F)
        
        # Embed
        x = self.embedding(x)  # (B*H*W, T, d_model)
        
        # Add positional encoding
        x = x + self.pos_encoding
        
        # Transformer
        x = self.transformer(x)  # (B*H*W, T, d_model)
        
        # Use last token
        x = x[:, -1, :]  # (B*H*W, d_model)
        
        # Decode
        x = self.dropout(x)
        x = self.fc_out(x)  # (B*H*W, 1)
        
        # Reshape back to (B, H*W)
        x = x.reshape(B, n_pixels)
        
        return x


class HydrometTransformerTorch:
    """
    PyTorch-based Hydromet Transformer for InSAR fusion.
    """
    
    def __init__(self, cfg: Optional[TransformerConfig] = None):
        """Initialize transformer."""
        self.cfg = cfg or TransformerConfig()
        self.model = TransformerEncoder(self.cfg)
        self.model.to(self.cfg.device)
        self.optimizer = optim.AdamW(
            self.model.parameters(),
            lr=self.cfg.learning_rate,
            weight_decay=self.cfg.weight_decay
        )
        self.criterion = nn.MSELoss()
        self.is_trained = False
        
        logger.info(f"Initialized HydrometTransformerTorch on {self.cfg.device}")
    
    def train_epoch(self, dataloader: DataLoader) -> float:
        """Train one epoch."""
        self.model.train()
        total_loss = 0.0
        n_batches = 0
        
        for seq, tgt in dataloader:
            seq = seq.to(self.cfg.device)  # (B, seq_len, H*W, F)
            tgt = tgt.to(self.cfg.device)  # (B, H*W)
            
            # Forward
            pred = self.model(seq)  # (B, H*W)
            
            # Compute loss
            loss = self.criterion(pred, tgt)
            
            # Backward
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()
            
            total_loss += loss.item()
            n_batches += 1
        
        avg_loss = total_loss / n_batches
        return avg_loss
    
    def validate(self, dataloader: DataLoader) -> Tuple[float, float]:
        """Validate model. Returns (MSE_loss, R²)."""
        self.model.eval()
        total_loss = 0.0
        all_pred = []
        all_tgt = []
        
        with torch.no_grad():
            for seq, tgt in dataloader:
                seq = seq.to(self.cfg.device)
                tgt = tgt.to(self.cfg.device)
                
                pred = self.model(seq)
                loss = self.criterion(pred, tgt)
                
                total_loss += loss.item()
                all_pred.append(pred.cpu().numpy())
                all_tgt.append(tgt.cpu().numpy())
        
        avg_loss = total_loss / len(dataloader)
        
        # Compute R²
        all_pred = np.concatenate(all_pred)
        all_tgt = np.concatenate(all_tgt)
        ss_res = np.sum((all_tgt - all_pred)**2)
        ss_tot = np.sum((all_tgt - np.mean(all_tgt))**2)
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        
        return avg_loss, r2
    
    def fit(self,
            train_data: np.ndarray,
            val_data: Optional[np.ndarray] = None,
            verbose: bool = True) -> Dict:
        """
        Train transformer on time series data.
        
        Args:
            train_data: Shape (T, H, W, F)
            val_data: Optional validation split
            verbose: Print progress
        
        Returns:
            Training history dict
        """
        # Create datasets
        train_dataset = TimeSeriesDataset(
            train_data,
            seq_length=self.cfg.seq_length,
            train=True
        )
        
        if val_data is None:
            val_dataset = TimeSeriesDataset(
                train_data,
                seq_length=self.cfg.seq_length,
                train=False
            )
        else:
            val_dataset = TimeSeriesDataset(
                val_data,
                seq_length=self.cfg.seq_length,
                train=True
            )
        
        train_loader = DataLoader(
            train_dataset,
            batch_size=self.cfg.batch_size,
            shuffle=True
        )
        val_loader = DataLoader(
            val_dataset,
            batch_size=self.cfg.batch_size,
            shuffle=False
        )
        
        logger.info(f"Training on {len(train_dataset)} sequences...")
        
        history = {
            'train_loss': [],
            'val_loss': [],
            'val_r2': []
        }
        
        best_val_loss = float('inf')
        patience_counter = 0
        
        for epoch in range(self.cfg.n_epochs):
            # Train
            train_loss = self.train_epoch(train_loader)
            
            # Validate
            val_loss, val_r2 = self.validate(val_loader)
            
            history['train_loss'].append(train_loss)
            history['val_loss'].append(val_loss)
            history['val_r2'].append(val_r2)
            
            if verbose and (epoch + 1) % 10 == 0:
                logger.info(
                    f"Epoch {epoch+1}/{self.cfg.n_epochs}: "
                    f"train_loss={train_loss:.4f}, "
                    f"val_loss={val_loss:.4f}, "
                    f"R²={val_r2:.4f}"
                )
            
            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
            else:
                patience_counter += 1
            
            if patience_counter >= self.cfg.early_stopping_patience:
                logger.info(f"Early stopping at epoch {epoch+1}")
                break
        
        self.is_trained = True
        logger.info("Training complete")
        return history
    
    def predict(self, data: np.ndarray) -> np.ndarray:
        """
        Predict displacement anomaly.
        
        Args:
            data: Shape (T, H, W, F)
        
        Returns:
            Predictions shape (T-seq_len, H, W)
        """
        if not self.is_trained:
            logger.warning("Model not trained, predictions may be poor")
        
        self.model.eval()
        
        T, H, W, F = data.shape
        data_flat = data.reshape(T, H*W, F)
        
        predictions = []
        
        with torch.no_grad():
            for i in range(T - self.cfg.seq_length):
                seq = torch.FloatTensor(
                    data_flat[i:i+self.cfg.seq_length]
                ).unsqueeze(0)  # (1, seq_len, H*W, F)
                
                seq = seq.to(self.cfg.device)
                pred = self.model(seq)  # (1, H*W)
                predictions.append(pred[0].cpu().numpy())
        
        predictions = np.array(predictions)  # (T-seq_len, H*W)
        predictions = predictions.reshape(-1, H, W)  # (T-seq_len, H, W)
        
        return predictions
    
    def save(self, path: Path):
        """Save model checkpoint."""
        torch.save({
            'model_state': self.model.state_dict(),
            'config': self.cfg,
            'is_trained': self.is_trained
        }, path)
        logger.info(f"Model saved to {path}")
    
    def load(self, path: Path):
        """Load model checkpoint."""
        checkpoint = torch.load(path, map_location=self.cfg.device)
        self.model.load_state_dict(checkpoint['model_state'])
        self.is_trained = checkpoint['is_trained']
        logger.info(f"Model loaded from {path}")


# Utility function
def train_transformer(
    los_timeseries: np.ndarray,
    hydro_data: np.ndarray,
    cfg: Optional[TransformerConfig] = None
) -> HydrometTransformerTorch:
    """
    Convenience function to train transformer.
    
    Example:
        model = train_transformer(
            los_ts,  # (T, H, W)
            hydro_data,  # (T, H, W, 4) = [P, SM, GWL, T]
            cfg
        )
    
    Returns:
        Trained model
    """
    # Stack features: [d_kalman, P, SM, GWL, T]
    T, H, W = los_timeseries.shape
    combined_data = np.zeros((T, H, W, 5))
    combined_data[:, :, :, 0] = los_timeseries
    combined_data[:, :, :, 1:] = hydro_data
    
    model = HydrometTransformerTorch(cfg)
    model.fit(combined_data, verbose=True)
    
    return model
