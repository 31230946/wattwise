"""
RatioModel: the XGBoost forecaster used for every horizon. It lives in its own small file
because the saved models in models/ are pickled instances of this class, so the app can
load them without importing the training code.
"""
import numpy as np
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit

SEED = 42


def new_xgb():
    return xgb.XGBRegressor(n_estimators=600, max_depth=4, learning_rate=0.05, subsample=0.8,
                            colsample_bytree=0.8, random_state=SEED, n_jobs=2, early_stopping_rounds=30)


def inner_split(df):
    gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=SEED)
    a, b = next(gss.split(df, groups=df["household_id"]))
    return df.iloc[a], df.iloc[b]


SHRINK_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)


class RatioModel:
    """XGBoost that predicts the CHANGE from a starting point (log of target / start), instead of
    raw kWh. Homes differ a lot in size but change in similar ways, so this carries over better
    to unseen homes. Choices made on held-back TRAINING homes only (never the test homes):
      * the starting point, from base_cols (e.g. last week vs. the 4-week average)
      * w, how much to trust the ML change (0 = just the starting point, 1 = full ML)."""

    def __init__(self, features, base_cols):
        self.features = features
        self.base_cols = [base_cols] if isinstance(base_cols, str) else list(base_cols)
        self.base_col, self.w, self.m = self.base_cols[0], 1.0, None

    @staticmethod
    def _b(df, col):
        return np.clip(df[col].values.astype(float), 0.05, None)

    def raw(self, df):
        return self._b(df, self.base_col) * np.exp(self.m.predict(df[self.features].values))

    def predict(self, df):
        return self.w * self.raw(df) + (1 - self.w) * self._b(df, self.base_col)

    def fit(self, train_df, target):
        fit, val = inner_split(train_df)
        y = val[target].values
        best = None
        for col in self.base_cols:
            ly = lambda d: np.log(np.clip(d[target].values, 0.05, None) / self._b(d, col))  # noqa: E731
            m = new_xgb()
            m.fit(fit[self.features].values, ly(fit), eval_set=[(val[self.features].values, ly(val))], verbose=False)
            base = self._b(val, col)
            raw = base * np.exp(m.predict(val[self.features].values))
            for w in SHRINK_GRID:
                err = np.abs(y - (w * raw + (1 - w) * base)).sum()
                if best is None or err < best[0]:
                    best = (err, col, w, m)
        _, self.base_col, self.w, self.m = best
        return self
