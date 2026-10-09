"""
SafeRouteAI - Visualization & Cartography
Author: SafeRouteAI Team

Responsible for all plotting and visualization routines:
1. High-resolution elevation-colored road network map (plasma colormap).
2. Standalone vehicle passability maps (RdYlGn colormap).
3. 3x3 scenario comparison grid (scenarios vs emergency vehicles).
"""

from typing import Dict, Optional, Tuple

import matplotlib.cm as cm
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox

from .config import (
    ELEVATION_PLOT_FILE,
    GRID_PLOT_DPI,
    GRID_PLOT_FILE,
    PLACE_NAME,
    PLOT_DPI,
    SCENARIOS,
    THEME_BG_COLOR,
    THEME_BORDER_COLOR,
    THEME_MUTED_COLOR,
    THEME_TEXT_COLOR,
    VEHICLES,
)
from .risk import passability, precompute_depressions


def plot_elevation_network(G: nx.MultiDiGraph, output_path: str = ELEVATION_PLOT_FILE) -> None:
    """
    Render and save the road network colored by minimum edge elevation (elev_min).

    Args:
        G: Road network graph with 'elev_min' edge attributes.
        output_path: Target PNG file path.
    """
    edge_elevations = [d["elev_min"] for _, _, _, d in G.edges(keys=True, data=True)]
    min_elev = min(edge_elevations)
    max_elev = max(edge_elevations)

    print(f"Rendering elevation network plot (range: {min_elev:.1f}m - {max_elev:.1f}m)...", flush=True)

    norm = mcolors.Normalize(vmin=min_elev, vmax=max_elev)
    cmap = plt.cm.plasma
    edge_colors = [cmap(norm(d["elev_min"])) for _, _, _, d in G.edges(keys=True, data=True)]

    fig, ax = plt.subplots(figsize=(11, 10), facecolor=THEME_BG_COLOR)

    ox.plot_graph(
        G,
        ax=ax,
        node_size=6,
        node_color="#444b58",
        node_alpha=0.45,
        edge_color=edge_colors,
        edge_linewidth=1.35,
        edge_alpha=0.92,
        bgcolor=THEME_BG_COLOR,
        show=False,
        close=False,
    )
    ax.set_facecolor(THEME_BG_COLOR)

    sm = cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, orientation="vertical", shrink=0.72, pad=0.03, aspect=26)
    cbar.set_label("Minimum Edge Elevation: elev_min (meters)", color=THEME_TEXT_COLOR, fontsize=10.5, labelpad=12)
    cbar.ax.yaxis.set_tick_params(color=THEME_MUTED_COLOR, labelcolor=THEME_TEXT_COLOR, labelsize=9)
    if hasattr(cbar, "outline") and cbar.outline is not None:
        cbar.outline.set_edgecolor(THEME_BORDER_COLOR)

    ax.set_title(
        f"SafeRouteAI — Road Network Elevation Model\n{PLACE_NAME} (2 km radius)",
        color=THEME_TEXT_COLOR,
        fontsize=13,
        pad=18,
        fontweight="bold",
    )

    fig.tight_layout()
    fig.savefig(output_path, dpi=PLOT_DPI, bbox_inches="tight", facecolor=THEME_BG_COLOR, edgecolor="none")
    plt.close(fig)
    print(f"Plot saved successfully: {output_path}", flush=True)


def plot_passability(
    G_assessed: nx.MultiDiGraph,
    vehicle: str,
    rainfall: float,
    river_level: float,
    output_path: Optional[str] = None,
    ax: Optional[plt.Axes] = None,
    show_colorbar: bool = True,
) -> plt.Axes:
    """
    Plot the road network colored by pass probability from Red (0.0) to Green (1.0).

    Args:
        G_assessed: Enriched road network with 'pass_probability' or 'pass_probability_<vehicle>'.
        vehicle: Vehicle identifier.
        rainfall: Rainfall intensity in mm/hr.
        river_level: River stage in meters.
        output_path: File path to save if standalone.
        ax: Existing matplotlib Axes to render into (for subplots).
        show_colorbar: Whether to render an individual colorbar.

    Returns:
        The matplotlib Axes containing the plot.
    """
    prob_key = f"pass_probability_{vehicle}"
    probs = [d.get(prob_key, d.get("pass_probability", 1.0)) for _, _, _, d in G_assessed.edges(keys=True, data=True)]

    cmap = plt.cm.RdYlGn
    norm = mcolors.Normalize(vmin=0.0, vmax=1.0)
    edge_colors = [cmap(norm(p)) for p in probs]

    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(11, 10), facecolor=THEME_BG_COLOR)
    else:
        fig = ax.figure

    ox.plot_graph(
        G_assessed,
        ax=ax,
        node_size=4,
        node_color="#333842",
        node_alpha=0.35,
        edge_color=edge_colors,
        edge_linewidth=1.3,
        edge_alpha=0.92,
        bgcolor=THEME_BG_COLOR,
        show=False,
        close=False,
    )
    ax.set_facecolor(THEME_BG_COLOR)

    impassable_count = sum(1 for p in probs if p < 0.5)
    impassable_pct = (impassable_count / len(probs)) * 100.0 if probs else 0.0

    vehicle_title = vehicle.replace("_", " ").title()
    ax.set_title(
        f"{vehicle_title} (Safe: {VEHICLES[vehicle]:.0f} cm)\n"
        f"River: {river_level:.1f} m | Rain: {rainfall:.0f} mm/hr | Closed: {impassable_pct:.1f}%",
        color=THEME_TEXT_COLOR,
        fontsize=10.5,
        pad=10,
        fontweight="bold",
    )

    if show_colorbar:
        sm = cm.ScalarMappable(norm=norm, cmap=cmap)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, orientation="vertical", shrink=0.72, pad=0.03, aspect=24)
        cbar.set_label("Pass Probability (1.0 = Safe, 0.0 = Impassable)", color=THEME_TEXT_COLOR, fontsize=9.5, labelpad=10)
        cbar.ax.yaxis.set_tick_params(color=THEME_MUTED_COLOR, labelcolor=THEME_TEXT_COLOR, labelsize=8.5)
        if hasattr(cbar, "outline") and cbar.outline is not None:
            cbar.outline.set_edgecolor(THEME_BORDER_COLOR)

    if standalone and output_path:
        fig.tight_layout()
        fig.savefig(output_path, dpi=PLOT_DPI, bbox_inches="tight", facecolor=THEME_BG_COLOR, edgecolor="none")
        plt.close(fig)
        print(f"Plot saved: {output_path}", flush=True)

    return ax


def plot_3x3_grid(
    G: nx.MultiDiGraph,
    scenarios: Dict[str, Dict[str, float]] = SCENARIOS,
    depressions: Optional[Dict[Tuple[int, int, int], float]] = None,
    output_path: str = GRID_PLOT_FILE,
) -> None:
    """
    Generate and save a 3x3 comparison grid across scenarios and emergency vehicles.

    Args:
        G: Base road network.
        scenarios: Scenario definitions dictionary.
        depressions: Precomputed edge depressions dictionary.
        output_path: Target PNG file path.
    """
    print("\nGenerating 3x3 scenario comparison grid plot...", flush=True)
    if depressions is None:
        depressions = precompute_depressions(G)

    vehicles_list = ["ambulance", "fire_tender", "rescue_truck"]
    fig, axes = plt.subplots(3, 3, figsize=(18, 18), facecolor=THEME_BG_COLOR)

    for row_idx, (scen_name, params) in enumerate(scenarios.items()):
        riv = params["river"]
        rain = params["rain"]

        for col_idx, v_name in enumerate(vehicles_list):
            ax = axes[row_idx, col_idx]
            G_eval = passability(G, v_name, rainfall=rain, river_level=riv, depressions=depressions)
            plot_passability(
                G_eval,
                vehicle=v_name,
                rainfall=rain,
                river_level=riv,
                ax=ax,
                show_colorbar=False,
            )

            if col_idx == 0:
                ax.annotate(
                    f"SCENARIO: {scen_name.upper()}",
                    xy=(0.03, 0.94),
                    xycoords="axes fraction",
                    color="#63b3ed",
                    fontsize=11,
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#1a202c", edgecolor="#4a5568", alpha=0.85),
                )

    fig.suptitle(
        "SafeRouteAI — Vehicle Passability Under Confluence Flood & Rain Scenarios\n"
        f"{PLACE_NAME} ({G.number_of_edges():,} road edges)",
        color="#ffffff",
        fontsize=16,
        fontweight="bold",
        y=0.995,
    )

    # Shared horizontal colorbar
    sm = cm.ScalarMappable(norm=mcolors.Normalize(vmin=0.0, vmax=1.0), cmap=plt.cm.RdYlGn)
    sm.set_array([])
    cbar_ax = fig.add_axes([0.25, 0.02, 0.50, 0.016])
    cbar = fig.colorbar(sm, cax=cbar_ax, orientation="horizontal")
    cbar.set_label("Pass Probability p  [ Red = Impassable (p < 0.5)  |  Green = Safe (p ≥ 0.5) ]",
                   color=THEME_TEXT_COLOR, fontsize=11, labelpad=8)
    cbar.ax.xaxis.set_tick_params(color=THEME_MUTED_COLOR, labelcolor=THEME_TEXT_COLOR, labelsize=9.5)
    if hasattr(cbar, "outline") and cbar.outline is not None:
        cbar.outline.set_edgecolor(THEME_BORDER_COLOR)

    fig.tight_layout(rect=[0.01, 0.045, 0.99, 0.98])
    fig.savefig(output_path, dpi=GRID_PLOT_DPI, bbox_inches="tight", facecolor=THEME_BG_COLOR, edgecolor="none")
    plt.close(fig)
    print(f"3x3 comparison grid saved successfully: {output_path}", flush=True)
