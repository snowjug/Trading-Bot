"""
Visual Analytics — Chart Generation with Plotly.

Generates interactive HTML charts for:
1. Equity curves (strategy vs benchmark)
2. Drawdown analysis
3. Regime timeline
4. Return distributions
5. Rolling Sharpe
6. Portfolio allocation
7. Event study CAR curves
8. Ablation sensitivity heatmaps
9. Correlation matrix
10. Trade scatter (MAE/MFE)
"""
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from src.utils.logging import setup_logging

logger = setup_logging("monitoring.charts")


# Color palette (dark theme)
COLORS = {
    "bg": "#0a0e17",
    "surface": "#131a2b",
    "accent": "#00d4ff",
    "accent2": "#7c4dff",
    "green": "#00e676",
    "red": "#ff1744",
    "yellow": "#ffd740",
    "orange": "#ff9100",
    "text": "#e0e0e0",
    "text_dim": "#8892a8",
    "grid": "#1e2a40",
}

STRATEGY_COLORS = [
    "#00d4ff", "#7c4dff", "#00e676", "#ff9100", "#ff1744",
    "#ffd740", "#e040fb", "#00bcd4", "#8bc34a", "#ff5722",
]

DARK_LAYOUT = dict(
    paper_bgcolor=COLORS["bg"],
    plot_bgcolor=COLORS["surface"],
    font=dict(color=COLORS["text"], family="Inter, Segoe UI, sans-serif"),
    xaxis=dict(gridcolor=COLORS["grid"], showgrid=True),
    yaxis=dict(gridcolor=COLORS["grid"], showgrid=True),
    margin=dict(l=60, r=40, t=60, b=40),
    legend=dict(
        bgcolor="rgba(19,26,43,0.8)",
        bordercolor=COLORS["grid"],
        borderwidth=1,
    ),
)


def equity_curve_chart(
    equity_curves: dict[str, pd.Series],
    title: str = "Equity Curves — Strategy vs Benchmarks",
    save_path: Optional[Path] = None,
) -> go.Figure:
    """
    Plot equity curves for multiple strategies/benchmarks.

    Args:
        equity_curves: dict of name -> equity Series (indexed by date)
        title: Chart title
        save_path: Optional path to save HTML
    """
    fig = go.Figure()

    for i, (name, eq) in enumerate(equity_curves.items()):
        if isinstance(eq, pd.DataFrame):
            if "datetime" in eq.columns and "equity" in eq.columns:
                eq = eq.set_index("datetime")["equity"]
            elif "equity" in eq.columns:
                eq = eq["equity"]
        color = STRATEGY_COLORS[i % len(STRATEGY_COLORS)]
        is_benchmark = "benchmark" in name.lower() or "buy" in name.lower()

        fig.add_trace(go.Scatter(
            x=eq.index,
            y=eq.values,
            name=name,
            line=dict(
                color=color,
                width=2 if not is_benchmark else 1,
                dash=None if not is_benchmark else "dash",
            ),
            opacity=1.0 if not is_benchmark else 0.7,
            hovertemplate=f"{name}<br>Date: %{{x}}<br>Value: Rs.%{{y:,.0f}}<extra></extra>",
        ))

    fig.update_layout(
        **DARK_LAYOUT,
        title=dict(text=title, font=dict(size=16)),
        yaxis_title="Portfolio Value (Rs.)",
        xaxis_title="Date",
        hovermode="x unified",
    )

    if save_path:
        fig.write_html(str(save_path))
        logger.info(f"Equity chart saved to {save_path}")

    return fig


def drawdown_chart(
    equity: pd.Series | pd.DataFrame,
    title: str = "Drawdown Analysis",
    save_path: Optional[Path] = None,
) -> go.Figure:
    """Plot drawdown underwater chart."""
    if isinstance(equity, pd.DataFrame):
        if "datetime" in equity.columns and "equity" in equity.columns:
            equity = equity.set_index("datetime")["equity"]
        elif "equity" in equity.columns:
            equity = equity["equity"]

    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax * 100

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.05,
        subplot_titles=("Equity Curve", "Drawdown (%)"),
    )

    # Equity curve
    fig.add_trace(go.Scatter(
        x=equity.index, y=equity.values,
        name="Equity",
        line=dict(color=COLORS["accent"], width=2),
        fill="tozeroy",
        fillcolor="rgba(0,212,255,0.05)",
    ), row=1, col=1)

    # Drawdown area
    fig.add_trace(go.Scatter(
        x=drawdown.index, y=drawdown.values,
        name="Drawdown",
        line=dict(color=COLORS["red"], width=1),
        fill="tozeroy",
        fillcolor="rgba(255,23,68,0.15)",
    ), row=2, col=1)

    # Max drawdown annotation
    max_dd_idx = drawdown.idxmin()
    max_dd_val = drawdown.min()
    fig.add_annotation(
        x=max_dd_idx, y=max_dd_val,
        text=f"Max DD: {max_dd_val:.1f}%",
        showarrow=True, arrowhead=2,
        font=dict(color=COLORS["red"]),
        row=2, col=1,
    )

    fig.update_layout(
        **DARK_LAYOUT,
        title=dict(text=title, font=dict(size=16)),
        showlegend=False,
        height=600,
    )

    if save_path:
        fig.write_html(str(save_path))

    return fig


def regime_timeline_chart(
    df: pd.DataFrame,
    title: str = "Market Regime Timeline",
    save_path: Optional[Path] = None,
) -> go.Figure:
    """Plot regime classification over time."""
    regime_colors = {
        "strong_bull": COLORS["green"],
        "weak_bull": "#81c784",
        "sideways": COLORS["yellow"],
        "weak_bear": "#ef9a9a",
        "strong_bear": COLORS["red"],
    }

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.05,
        subplot_titles=("Price & Regime", "Regime Classification"),
    )

    # Price chart
    fig.add_trace(go.Scatter(
        x=df["datetime"], y=df["close"],
        name="Close",
        line=dict(color=COLORS["text"], width=1),
    ), row=1, col=1)

    # Color background by regime
    regime_col = "trend_regime" if "trend_regime" in df.columns else "hmm_regime"
    if regime_col in df.columns:
        for regime, color in regime_colors.items():
            mask = df[regime_col] == regime
            if mask.any():
                regime_data = df.loc[mask]
                fig.add_trace(go.Scatter(
                    x=regime_data["datetime"],
                    y=regime_data["close"],
                    mode="markers",
                    name=regime.replace("_", " ").title(),
                    marker=dict(color=color, size=3, opacity=0.6),
                ), row=1, col=1)

    # Regime bar
    if regime_col in df.columns:
        regime_numeric = df[regime_col].map({
            "strong_bear": -2, "weak_bear": -1, "sideways": 0,
            "weak_bull": 1, "strong_bull": 2,
        }).fillna(0)

        colors = [regime_colors.get(r, COLORS["text_dim"]) for r in df[regime_col]]

        fig.add_trace(go.Bar(
            x=df["datetime"],
            y=regime_numeric,
            name="Regime",
            marker_color=colors,
            opacity=0.7,
            showlegend=False,
        ), row=2, col=1)

    fig.update_layout(
        **DARK_LAYOUT,
        title=dict(text=title, font=dict(size=16)),
        height=600,
    )

    if save_path:
        fig.write_html(str(save_path))

    return fig


def return_distribution_chart(
    returns: pd.Series | pd.DataFrame,
    strategy_name: str = "Strategy",
    save_path: Optional[Path] = None,
) -> go.Figure:
    """Plot return distribution with normal overlay."""
    if isinstance(returns, pd.DataFrame):
        if "returns" in returns.columns:
            returns = returns["returns"].dropna()
        elif "equity" in returns.columns:
            returns = returns["equity"].pct_change().dropna()
        else:
            returns = returns.iloc[:, 0].dropna()
    elif isinstance(returns, pd.Series):
        returns = returns.dropna()

    fig = go.Figure()

    # Histogram
    fig.add_trace(go.Histogram(
        x=returns.values * 100,
        nbinsx=50,
        name="Actual Returns",
        marker_color=COLORS["accent"],
        opacity=0.7,
    ))

    # Normal distribution overlay
    mu = returns.mean() * 100
    sigma = returns.std() * 100
    x_range = np.linspace(mu - 4 * sigma, mu + 4 * sigma, 100)
    normal_pdf = (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(
        -0.5 * ((x_range - mu) / sigma) ** 2
    )

    # Scale PDF to match histogram
    bin_width = (returns.max() - returns.min()) * 100 / 50
    normal_scaled = normal_pdf * len(returns) * bin_width

    fig.add_trace(go.Scatter(
        x=x_range, y=normal_scaled,
        name="Normal Distribution",
        line=dict(color=COLORS["yellow"], width=2, dash="dash"),
    ))

    # Stats annotations
    from scipy.stats import skew, kurtosis
    sk = skew(returns.dropna())
    ku = kurtosis(returns.dropna())

    fig.add_annotation(
        text=(
            f"Mean: {mu:.3f}%<br>"
            f"Std: {sigma:.3f}%<br>"
            f"Skew: {sk:.2f}<br>"
            f"Kurtosis: {ku:.2f}"
        ),
        xref="paper", yref="paper",
        x=0.95, y=0.95,
        showarrow=False,
        font=dict(size=11, color=COLORS["text"]),
        bgcolor="rgba(19,26,43,0.9)",
        bordercolor=COLORS["grid"],
    )

    fig.update_layout(
        **DARK_LAYOUT,
        title=dict(text=f"Return Distribution — {strategy_name}", font=dict(size=16)),
        xaxis_title="Daily Return (%)",
        yaxis_title="Frequency",
    )

    if save_path:
        fig.write_html(str(save_path))

    return fig


def rolling_sharpe_chart(
    returns: pd.Series,
    window: int = 63,
    strategy_name: str = "Strategy",
    save_path: Optional[Path] = None,
) -> go.Figure:
    """Plot rolling Sharpe ratio over time."""
    rolling_ret = returns.rolling(window).mean() * 252
    rolling_vol = returns.rolling(window).std() * np.sqrt(252)
    rolling_sharpe = rolling_ret / rolling_vol.replace(0, np.nan)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=rolling_sharpe.index,
        y=rolling_sharpe.values,
        name=f"{window}-day Rolling Sharpe",
        line=dict(color=COLORS["accent"], width=2),
    ))

    # Add zero line
    fig.add_hline(y=0, line=dict(color=COLORS["text_dim"], dash="dash", width=1))

    # Add 1.0 and -1.0 reference lines
    fig.add_hline(y=1.0, line=dict(color=COLORS["green"], dash="dot", width=1))
    fig.add_hline(y=-1.0, line=dict(color=COLORS["red"], dash="dot", width=1))

    # Color fill: green above 0, red below 0
    fig.add_trace(go.Scatter(
        x=rolling_sharpe.index,
        y=rolling_sharpe.clip(lower=0).values,
        fill="tozeroy",
        fillcolor="rgba(0,230,118,0.1)",
        line=dict(width=0),
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=rolling_sharpe.index,
        y=rolling_sharpe.clip(upper=0).values,
        fill="tozeroy",
        fillcolor="rgba(255,23,68,0.1)",
        line=dict(width=0),
        showlegend=False,
    ))

    fig.update_layout(
        **DARK_LAYOUT,
        title=dict(
            text=f"Rolling Sharpe Ratio ({window}-day) — {strategy_name}",
            font=dict(size=16),
        ),
        yaxis_title="Sharpe Ratio",
        xaxis_title="Date",
    )

    if save_path:
        fig.write_html(str(save_path))

    return fig


def portfolio_allocation_chart(
    allocations: dict[str, float],
    title: str = "Portfolio Allocation",
    save_path: Optional[Path] = None,
) -> go.Figure:
    """Sunburst/pie chart for portfolio allocation."""
    names = list(allocations.keys())
    weights = list(allocations.values())

    fig = go.Figure(go.Pie(
        labels=names,
        values=[w * 100 for w in weights],
        hole=0.45,
        marker=dict(
            colors=STRATEGY_COLORS[:len(names)],
            line=dict(color=COLORS["bg"], width=2),
        ),
        textinfo="label+percent",
        textfont=dict(color=COLORS["text"], size=11),
        hovertemplate="%{label}<br>Weight: %{value:.1f}%<extra></extra>",
    ))

    fig.update_layout(
        **DARK_LAYOUT,
        title=dict(text=title, font=dict(size=16)),
        annotations=[dict(
            text="Allocation",
            x=0.5, y=0.5,
            font=dict(size=14, color=COLORS["text_dim"]),
            showarrow=False,
        )],
    )

    if save_path:
        fig.write_html(str(save_path))

    return fig


def correlation_matrix_chart(
    returns: pd.DataFrame,
    title: str = "Strategy Return Correlations",
    save_path: Optional[Path] = None,
) -> go.Figure:
    """Heatmap of strategy return correlations."""
    corr = returns.corr()

    fig = go.Figure(go.Heatmap(
        z=corr.values,
        x=corr.columns,
        y=corr.index,
        colorscale=[
            [0, COLORS["red"]],
            [0.5, COLORS["bg"]],
            [1, COLORS["green"]],
        ],
        zmin=-1, zmax=1,
        text=np.round(corr.values, 2),
        texttemplate="%{text}",
        textfont=dict(size=10, color=COLORS["text"]),
        hovertemplate="%{x} vs %{y}<br>Correlation: %{z:.3f}<extra></extra>",
    ))

    fig.update_layout(
        **DARK_LAYOUT,
        title=dict(text=title, font=dict(size=16)),
        height=500,
        width=600,
    )

    if save_path:
        fig.write_html(str(save_path))

    return fig


def ablation_heatmap(
    perturbations: list[dict],
    strategy_name: str = "Strategy",
    save_path: Optional[Path] = None,
) -> go.Figure:
    """Heatmap of parameter sensitivity from ablation testing."""
    if not perturbations:
        fig = go.Figure()
        fig.update_layout(**DARK_LAYOUT, title="No ablation data")
        return fig

    df = pd.DataFrame(perturbations)

    # Pivot: params vs perturbation_pct
    pivot = df.pivot_table(
        values="sharpe_retention",
        index="param",
        columns="perturbation_pct",
        aggfunc="mean",
    )

    fig = go.Figure(go.Heatmap(
        z=pivot.values * 100,
        x=[f"{p:+.0%}" for p in pivot.columns],
        y=pivot.index,
        colorscale=[
            [0, COLORS["red"]],
            [0.5, COLORS["yellow"]],
            [1, COLORS["green"]],
        ],
        zmin=0, zmax=150,
        text=np.round(pivot.values * 100, 0),
        texttemplate="%{text:.0f}%",
        textfont=dict(size=10, color=COLORS["text"]),
        colorbar=dict(title="Sharpe Retention %"),
    ))

    fig.update_layout(
        **DARK_LAYOUT,
        title=dict(
            text=f"Parameter Sensitivity — {strategy_name}",
            font=dict(size=16),
        ),
        xaxis_title="Parameter Perturbation",
        yaxis_title="Parameter",
        height=400,
    )

    if save_path:
        fig.write_html(str(save_path))

    return fig


def event_study_car_chart(
    event_windows: list,
    event_type: str = "Event",
    save_path: Optional[Path] = None,
) -> go.Figure:
    """
    Plot cumulative abnormal return curves for event study.
    Shows individual event CARs plus the average.
    """
    fig = go.Figure()

    if not event_windows:
        fig.update_layout(**DARK_LAYOUT, title="No event data")
        return fig

    # Each event's CAR curve
    all_cars = []
    for i, window in enumerate(event_windows):
        full_returns = window.pre_event_returns + window.post_event_returns
        car = np.cumsum(full_returns)
        t_axis = list(range(-len(window.pre_event_returns), len(window.post_event_returns)))

        all_cars.append(car)

        fig.add_trace(go.Scatter(
            x=t_axis,
            y=car * 100,
            name=f"Event {i+1}",
            line=dict(color=COLORS["text_dim"], width=0.5),
            opacity=0.3,
            showlegend=False,
        ))

    # Average CAR
    if all_cars:
        max_len = max(len(c) for c in all_cars)
        padded = np.array([
            np.pad(c, (0, max_len - len(c)), constant_values=c[-1])
            for c in all_cars
        ])
        avg_car = padded.mean(axis=0)
        t_axis = list(range(-len(event_windows[0].pre_event_returns),
                            max_len - len(event_windows[0].pre_event_returns)))

        fig.add_trace(go.Scatter(
            x=t_axis[:len(avg_car)],
            y=avg_car * 100,
            name="Average CAR",
            line=dict(color=COLORS["accent"], width=3),
        ))

    # Event date line
    fig.add_vline(x=0, line=dict(color=COLORS["yellow"], dash="dash", width=2))
    fig.add_annotation(
        x=0, y=0, text="Event Date",
        showarrow=True, arrowhead=2,
        font=dict(color=COLORS["yellow"]),
    )

    fig.update_layout(
        **DARK_LAYOUT,
        title=dict(
            text=f"Cumulative Abnormal Returns — {event_type}",
            font=dict(size=16),
        ),
        xaxis_title="Trading Days Relative to Event",
        yaxis_title="CAR (%)",
    )

    if save_path:
        fig.write_html(str(save_path))

    return fig


def generate_full_report_charts(
    output_dir: Path,
    equity_curves: dict = None,
    strategy_returns: pd.DataFrame = None,
    regime_df: pd.DataFrame = None,
    allocations: dict = None,
    ablation_results: list = None,
    event_results: list = None,
) -> list[Path]:
    """
    Generate all charts for the institutional report.

    Returns list of generated file paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    if equity_curves:
        p = output_dir / "equity_curves.html"
        equity_curve_chart(equity_curves, save_path=p)
        generated.append(p)

    if strategy_returns is not None and not strategy_returns.empty:
        for col in strategy_returns.columns[:5]:
            p = output_dir / f"drawdown_{col}.html"
            eq = (1 + strategy_returns[col]).cumprod() * 1_000_000
            drawdown_chart(eq, title=f"Drawdown — {col}", save_path=p)
            generated.append(p)

            p = output_dir / f"returns_dist_{col}.html"
            return_distribution_chart(
                strategy_returns[col], strategy_name=col, save_path=p
            )
            generated.append(p)

            p = output_dir / f"rolling_sharpe_{col}.html"
            rolling_sharpe_chart(
                strategy_returns[col], strategy_name=col, save_path=p
            )
            generated.append(p)

        p = output_dir / "correlation_matrix.html"
        correlation_matrix_chart(strategy_returns, save_path=p)
        generated.append(p)

    if regime_df is not None and not regime_df.empty:
        p = output_dir / "regime_timeline.html"
        regime_timeline_chart(regime_df, save_path=p)
        generated.append(p)

    if allocations:
        p = output_dir / "portfolio_allocation.html"
        portfolio_allocation_chart(allocations, save_path=p)
        generated.append(p)

    if ablation_results:
        for abl in ablation_results:
            if abl.perturbations:
                p = output_dir / f"ablation_{abl.strategy_name}.html"
                ablation_heatmap(
                    abl.perturbations,
                    strategy_name=abl.strategy_name,
                    save_path=p,
                )
                generated.append(p)

    if event_results:
        for evt in event_results:
            if evt and evt.event_windows:
                p = output_dir / f"event_study_{evt.event_type}.html"
                event_study_car_chart(
                    evt.event_windows,
                    event_type=evt.event_type,
                    save_path=p,
                )
                generated.append(p)

    logger.info(f"Generated {len(generated)} charts in {output_dir}")
    return generated
