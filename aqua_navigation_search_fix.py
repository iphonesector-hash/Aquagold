"""Ensure final branch search uses Search API with Geocoding Plus fallback."""
import app_v3
import aqua_navigation_polish

if "smart_tour_place_search" in app_v3.app.view_functions:
    app_v3.app.view_functions["smart_tour_place_search"] = aqua_navigation_polish._polished_place_search
