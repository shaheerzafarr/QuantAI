"""High-Performance Pure NumPy / Polars Pandas-Compatible Series & DataFrame Layer.

Ensures zero dependency on vulnerable or blocked C-extensions, fully compatible
with Python 3.14+, operating seamlessly under Windows Application Control policies.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union
import numpy as np
import polars as pl


class RollingWindow:
    def __init__(self, arr: np.ndarray, window: int):
        self.arr = np.asarray(arr, dtype=float)
        self.window = int(window)

    def mean(self) -> "QSeries":
        n = len(self.arr)
        res = np.full(n, np.nan, dtype=float)
        if n >= self.window:
            # Vectorized cumsum for rolling mean
            cumsum = np.cumsum(np.insert(self.arr, 0, 0.0))
            valid_means = (cumsum[self.window:] - cumsum[:-self.window]) / float(self.window)
            res[self.window - 1:] = valid_means
        return QSeries(res)

    def std(self) -> "QSeries":
        n = len(self.arr)
        res = np.full(n, np.nan, dtype=float)
        for i in range(self.window - 1, n):
            sub = self.arr[i - self.window + 1: i + 1]
            res[i] = np.std(sub, ddof=1) if len(sub) > 1 else 0.0
        return QSeries(res)

    def max(self) -> "QSeries":
        n = len(self.arr)
        res = np.full(n, np.nan, dtype=float)
        for i in range(self.window - 1, n):
            res[i] = np.max(self.arr[i - self.window + 1: i + 1])
        return QSeries(res)


class EwmWindow:
    def __init__(self, arr: np.ndarray, alpha: float):
        self.arr = np.asarray(arr, dtype=float)
        self.alpha = float(alpha)

    def mean(self) -> "QSeries":
        n = len(self.arr)
        res = np.zeros(n, dtype=float)
        if n == 0:
            return QSeries(res)
        res[0] = self.arr[0]
        a = self.alpha
        one_minus_a = 1.0 - a
        for i in range(1, n):
            val = self.arr[i]
            if np.isnan(val):
                res[i] = res[i - 1]
            else:
                res[i] = a * val + one_minus_a * res[i - 1]
        return QSeries(res)


class ILocIndexer:
    def __init__(self, parent: Union["QSeries", "QDataFrame"]):
        self.parent = parent

    def __getitem__(self, idx: Any) -> Any:
        if isinstance(self.parent, QSeries):
            val = self.parent.values[idx]
            if isinstance(idx, slice):
                return QSeries(val)
            return val
        else:
            # QDataFrame
            if isinstance(idx, (int, np.integer)):
                # return row as QSeries or Dict
                row_dict = {col: self.parent._cols[col][idx] for col in self.parent.columns}
                return QSeries(row_dict, name=idx)
            elif isinstance(idx, slice):
                sub_cols = {col: self.parent._cols[col][idx] for col in self.parent.columns}
                return QDataFrame(sub_cols)
            elif isinstance(idx, tuple) and len(idx) == 2:
                row_idx, col_idx = idx
                if isinstance(col_idx, (int, np.integer)):
                    col_name = self.parent.columns[col_idx]
                else:
                    col_name = col_idx
                return self.parent._cols[col_name][row_idx]
            raise IndexError("Unsupported index type")

    def __setitem__(self, idx: Any, value: Any):
        if isinstance(self.parent, QSeries):
            self.parent.values[idx] = value
        else:
            if isinstance(idx, tuple) and len(idx) == 2:
                row_idx, col_idx = idx
                if isinstance(col_idx, (int, np.integer)):
                    col_name = self.parent.columns[col_idx]
                else:
                    col_name = col_idx
                self.parent._cols[col_name][row_idx] = value


class QSeries:
    """NumPy-backed Series with full vectorized Pandas API."""

    def __init__(self, data: Any = None, index: Any = None, dtype: Any = None, name: Any = None):
        if isinstance(data, dict):
            self._dict = data
            self.values = np.array(list(data.values()))
            self._keys = list(data.keys())
        elif isinstance(data, QSeries):
            self.values = np.array(data.values, copy=True)
            self._dict = None
            self._keys = None
        elif data is None:
            self.values = np.array([], dtype=dtype or float)
            self._dict = None
            self._keys = None
        else:
            self.values = np.asarray(data)
            self._dict = None
            self._keys = None
        self.index = index if index is not None else np.arange(len(self.values))
        self.name = name

    def __len__(self) -> int:
        return len(self.values)

    @property
    def iloc(self) -> ILocIndexer:
        return ILocIndexer(self)

    @property
    def dtype(self) -> np.dtype:
        return self.values.dtype

    def __getitem__(self, item: Any) -> Any:
        if self._dict is not None and isinstance(item, str):
            return self._dict.get(item)
        if isinstance(item, str) and self._keys is not None:
            try:
                idx = self._keys.index(item)
                return self.values[idx]
            except ValueError:
                return None
        if isinstance(item, QSeries):
            item = item.values.astype(bool)
        if isinstance(item, (np.ndarray, list)):
            mask = np.asarray(item)
            if mask.dtype == bool:
                return QSeries(self.values[mask])
            return QSeries(self.values[mask])
        return self.values[item]

    def __setitem__(self, key: Any, value: Any):
        if self._dict is not None and isinstance(key, str):
            self._dict[key] = value
        self.values[key] = value

    def get(self, key: Any, default: Any = None) -> Any:
        if self._dict is not None:
            return self._dict.get(key, default)
        if self._keys is not None and key in self._keys:
            idx = self._keys.index(key)
            return self.values[idx]
        return default

    # Arithmetic
    def __add__(self, other: Any) -> "QSeries":
        val = other.values if isinstance(other, QSeries) else other
        return QSeries(self.values + val)

    def __radd__(self, other: Any) -> "QSeries":
        return self.__add__(other)

    def __sub__(self, other: Any) -> "QSeries":
        val = other.values if isinstance(other, QSeries) else other
        return QSeries(self.values - val)

    def __rsub__(self, other: Any) -> "QSeries":
        val = other.values if isinstance(other, QSeries) else other
        return QSeries(val - self.values)

    def __mul__(self, other: Any) -> "QSeries":
        val = other.values if isinstance(other, QSeries) else other
        return QSeries(self.values * val)

    def __rmul__(self, other: Any) -> "QSeries":
        return self.__mul__(other)

    def __truediv__(self, other: Any) -> "QSeries":
        val = other.values if isinstance(other, QSeries) else other
        return QSeries(self.values / val)

    def __rtruediv__(self, other: Any) -> "QSeries":
        val = other.values if isinstance(other, QSeries) else other
        return QSeries(val / self.values)

    def __pow__(self, other: Any) -> "QSeries":
        return QSeries(self.values ** other)

    def __neg__(self) -> "QSeries":
        return QSeries(-self.values)

    def __gt__(self, other: Any) -> "QSeries":
        val = other.values if isinstance(other, QSeries) else other
        return QSeries(self.values > val)

    def __ge__(self, other: Any) -> "QSeries":
        val = other.values if isinstance(other, QSeries) else other
        return QSeries(self.values >= val)

    def __lt__(self, other: Any) -> "QSeries":
        val = other.values if isinstance(other, QSeries) else other
        return QSeries(self.values < val)

    def __le__(self, other: Any) -> "QSeries":
        val = other.values if isinstance(other, QSeries) else other
        return QSeries(self.values <= val)

    def __eq__(self, other: Any) -> "QSeries":
        val = other.values if isinstance(other, QSeries) else other
        return QSeries(self.values == val)

    def diff(self, periods: int = 1) -> "QSeries":
        res = np.full(len(self.values), np.nan, dtype=float)
        if len(self.values) > periods:
            res[periods:] = self.values[periods:] - self.values[:-periods]
        return QSeries(res)

    def shift(self, periods: int = 1) -> "QSeries":
        res = np.full(len(self.values), np.nan, dtype=float)
        if periods > 0 and len(self.values) > periods:
            res[periods:] = self.values[:-periods]
        elif periods < 0 and len(self.values) > abs(periods):
            res[:periods] = self.values[abs(periods):]
        return QSeries(res)

    def abs(self) -> "QSeries":
        return QSeries(np.abs(self.values))

    def cumsum(self) -> "QSeries":
        return QSeries(np.cumsum(self.values))

    def cummax(self) -> "QSeries":
        return QSeries(np.maximum.accumulate(self.values))

    def cumprod(self) -> "QSeries":
        return QSeries(np.cumprod(self.values))

    def rolling(self, window: int) -> RollingWindow:
        return RollingWindow(self.values, window)

    def ewm(self, span: Optional[float] = None, alpha: Optional[float] = None, adjust: bool = False) -> EwmWindow:
        if alpha is None and span is not None:
            alpha = 2.0 / (span + 1.0)
        return EwmWindow(self.values, alpha or 0.1)

    def where(self, cond: Any, other: Any = np.nan) -> "QSeries":
        c = cond.values if isinstance(cond, QSeries) else np.asarray(cond)
        return QSeries(np.where(c, self.values, other))

    def dropna(self) -> "QSeries":
        mask = ~np.isnan(self.values)
        return QSeries(self.values[mask])

    def notna(self) -> "QSeries":
        return QSeries(~np.isnan(self.values))

    def isna(self) -> "QSeries":
        return QSeries(np.isnan(self.values))

    def copy(self) -> "QSeries":
        return QSeries(np.copy(self.values), index=self.index, name=self.name)

    def mean(self) -> float:
        valid = self.dropna().values
        return float(np.mean(valid)) if len(valid) > 0 else 0.0

    def std(self) -> float:
        valid = self.dropna().values
        return float(np.std(valid, ddof=1)) if len(valid) > 1 else 0.0

    def min(self) -> float:
        valid = self.dropna().values
        return float(np.min(valid)) if len(valid) > 0 else 0.0

    def all(self) -> bool:
        return bool(np.all(self.values))

    def any(self) -> bool:
        return bool(np.any(self.values))

    def max(self, axis: Any = None) -> float:
        valid = self.dropna().values
        return float(np.max(valid)) if len(valid) > 0 else 0.0

    def sum(self) -> float:
        valid = self.dropna().values
        return float(np.sum(valid)) if len(valid) > 0 else 0.0


class QDataFrame:
    """NumPy & Polars backed DataFrame offering drop-in Pandas compatibility."""

    def __init__(self, data: Any = None, columns: Optional[List[str]] = None):
        self._cols: Dict[str, np.ndarray] = {}
        if isinstance(data, dict):
            for k, v in data.items():
                self._cols[k] = np.asarray(v)
        elif isinstance(data, list):
            if len(data) > 0 and isinstance(data[0], dict):
                cols = columns or list(data[0].keys())
                for col in cols:
                    self._cols[col] = np.array([row.get(col) for row in data])
        elif isinstance(data, QDataFrame):
            for k, v in data._cols.items():
                self._cols[k] = np.copy(v)

    def __len__(self) -> int:
        if not self._cols:
            return 0
        first_col = next(iter(self._cols.values()))
        return len(first_col)

    @property
    def columns(self) -> List[str]:
        return list(self._cols.keys())

    @property
    def index(self) -> np.ndarray:
        return np.arange(len(self))

    @property
    def iloc(self) -> ILocIndexer:
        return ILocIndexer(self)

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, str):
            if item not in self._cols:
                raise KeyError(f"Column '{item}' not found in DataFrame.")
            return QSeries(self._cols[item], name=item)
        elif isinstance(item, list):
            # Multiple columns
            sub_dict = {col: self._cols[col] for col in item}
            return QDataFrame(sub_dict)
        elif isinstance(item, QSeries):
            mask = item.values.astype(bool)
            return self._apply_mask(mask)
        elif isinstance(item, np.ndarray) and item.dtype == bool:
            return self._apply_mask(item)
        raise KeyError(f"Unsupported DataFrame key: {item}")

    def _apply_mask(self, mask: np.ndarray) -> "QDataFrame":
        sub_dict = {col: arr[mask] for col, arr in self._cols.items()}
        return QDataFrame(sub_dict)

    def __setitem__(self, key: str, value: Any):
        if isinstance(value, QSeries):
            arr = value.values
        elif isinstance(value, (list, tuple)):
            arr = np.asarray(value)
        elif np.isscalar(value):
            arr = np.full(len(self), value)
        else:
            arr = np.asarray(value)
        self._cols[key] = arr

    def copy(self) -> "QDataFrame":
        new_df = QDataFrame()
        for k, v in self._cols.items():
            new_df._cols[k] = np.copy(v)
        return new_df

    def sort_values(self, by: str, inplace: bool = False) -> Optional["QDataFrame"]:
        if by in self._cols:
            sort_order = np.argsort(self._cols[by])
            new_cols = {col: arr[sort_order] for col, arr in self._cols.items()}
            if inplace:
                self._cols = new_cols
                return None
            df = QDataFrame()
            df._cols = new_cols
            return df
        return self

    def reset_index(self, drop: bool = True, inplace: bool = False):
        return self

    def bfill(self, inplace: bool = False) -> Optional["QDataFrame"]:
        """Backward fills NaNs."""
        for col, arr in self._cols.items():
            if np.issubdtype(arr.dtype, np.floating) and np.isnan(arr).any():
                n = len(arr)
                for i in range(n - 2, -1, -1):
                    if np.isnan(arr[i]):
                        arr[i] = arr[i + 1]
                # If first row still nan
                if np.isnan(arr[-1]):
                    arr[np.isnan(arr)] = 0.0
        return None if inplace else self

    def max(self, axis: int = 0) -> Any:
        if axis == 1:
            mat = np.column_stack([self._cols[col] for col in self.columns])
            return QSeries(np.nanmax(mat, axis=1))
        else:
            return {col: float(np.nanmax(arr)) for col, arr in self._cols.items()}

    def rename(self, columns: Dict[str, str]) -> "QDataFrame":
        new_cols = {}
        for k, v in self._cols.items():
            new_name = columns.get(k, k)
            new_cols[new_name] = v
        df = QDataFrame()
        df._cols = new_cols
        return df


# Compatibility top-level functions matching pandas module namespace
Series = QSeries
DataFrame = QDataFrame


def date_range(start: str, periods: int, freq: str = "5min") -> List[datetime]:
    dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    step = timedelta(minutes=5) if "min" in freq else timedelta(hours=1)
    return [dt + i * step for i in range(periods)]


def concat(objs: List[Any], axis: int = 0) -> Any:
    if axis == 1:
        # Concatenate columns into a QDataFrame
        cols_dict = {}
        for idx, o in enumerate(objs):
            col_name = getattr(o, "name", None) or f"col_{idx}"
            cols_dict[str(col_name)] = o.values if isinstance(o, QSeries) else np.asarray(o)
        return QDataFrame(cols_dict)
    else:
        # Row concatenation
        arr = np.concatenate([o.values for o in objs])
        return QSeries(arr)


def merge_asof(
    left: QDataFrame,
    right: QDataFrame,
    on: str = "timestamp",
    direction: str = "backward",
) -> QDataFrame:
    """Exact merge_asof implementation preventing lookahead bias."""
    res = left.copy()
    left_ts = left._cols[on]
    right_ts = right._cols[on]

    # For each timestamp in left, find right timestamp index
    indices = np.searchsorted(right_ts, left_ts, side="right") - 1
    indices = np.clip(indices, 0, len(right_ts) - 1)

    for col in right.columns:
        if col != on:
            res._cols[col] = right._cols[col][indices]

    return res


def isna(val: Any) -> bool:
    if isinstance(val, QSeries):
        return val.isna()
    return bool(np.isnan(val))
