#!/usr/bin/env Rscript
# ============================================================================
# Regulation Preparedness Figures
# ============================================================================
#
# This script reads pre-computed regulation preparedness scores from the
# Python scoring pipeline (nlp_contextual_scoring.py) and generates
# publication-quality figures + spatial exports.
#
# PREREQUISITE: Run python3 analysis/scripts/nlp_contextual_scoring.py first.
#
# INPUT:
#   outputs/latest/regulation_scores.csv
#   outputs/latest/derived/fix_impact_summary.csv
#   data/Navigator_AllSites_032825_shp/Navigator_AllSites_032825.shp
#
# OUTPUT:
#   Figures 1, 2, S1, S2 (PNG + PDF)
#   outputs/latest/mpa_scores_spatial.gpkg
#
# ============================================================================

suppressPackageStartupMessages({
  library(tidyverse)
  library(sf)
  library(scales)
  library(patchwork)
  library(jsonlite)
})

root_dir <- "/Volumes/bacdrive/Dropbox/Work/technology_for_IUU_monitoring"
output_dir <- file.path(root_dir, "outputs/latest")
figure_dir <- file.path(output_dir, "figures")
dir.create(figure_dir, showWarnings = FALSE, recursive = TRUE)

cat("=" |> rep(70) |> paste(collapse = ""), "\n")
cat("REGULATION PREPAREDNESS FIGURES\n")
cat("=" |> rep(70) |> paste(collapse = ""), "\n\n")

# ============================================================================
# 1. LOAD PRE-COMPUTED SCORES
# ============================================================================

cat("Step 1: Loading pre-computed scores...\n")
scores_path <- file.path(output_dir, "regulation_scores.csv")
if (!file.exists(scores_path)) {
  stop("Scores not found. Run: python3 analysis/scripts/nlp_contextual_scoring.py")
}

site_scores <- read_csv(scores_path, show_col_types = FALSE)
cat(sprintf("  Loaded %s scored MPAs from %s countries\n",
            format(nrow(site_scores), big.mark = ","),
            n_distinct(site_scores$country)))

mean_prep <- mean(site_scores$preparedness_score)
median_prep <- median(site_scores$preparedness_score)
pct_low <- mean(site_scores$preparedness_score <= 30) * 100
pct_high <- mean(site_scores$preparedness_score >= 70) * 100
mean_improved <- mean(site_scores$improved_score)
pct_increase <- (mean_improved - mean_prep) / mean_prep * 100

cat(sprintf("  Mean: %.1f | Median: %.1f | <=30: %.1f%% | >=70: %.1f%%\n",
            mean_prep, median_prep, pct_low, pct_high))
cat(sprintf("  After fixes: %.1f (+%.0f%%)\n", mean_improved, pct_increase))

# ============================================================================
# 2. LOAD SPATIAL DATA
# ============================================================================

cat("\nStep 2: Loading spatial data...\n")
shapefile_path <- file.path(root_dir, "data/Navigator_AllSites_032825_shp/Navigator_AllSites_032825.shp")
sf_use_s2(FALSE)
mpa_shapes <- st_read(shapefile_path, quiet = TRUE) |>
  st_transform(4326) |>
  st_make_valid()

site_scores_spatial <- mpa_shapes |>
  mutate(site_id_upper = toupper(SITE_ID)) |>
  left_join(
    site_scores |> mutate(site_id_upper = toupper(site_id)),
    by = "site_id_upper"
  ) |>
  filter(!is.na(preparedness_score))

cat(sprintf("  Matched %s of %s sites\n", nrow(site_scores_spatial), nrow(site_scores)))

# ============================================================================
# 3. FIGURES
# ============================================================================

cat("\nStep 3: Creating figures...\n")

prep_palette <- c("#A50026", "#F46D43", "#FDAE61", "#74ADD1", "#4575B4", "#313695")

theme_pub <- function(base_size = 14) {
  theme_minimal(base_size = base_size) +
    theme(
      text = element_text(family = "sans"),
      plot.background = element_rect(fill = "white", color = NA),
      panel.background = element_rect(fill = "white", color = NA),
      panel.grid.major = element_line(color = "gray90", linewidth = 0.3),
      panel.grid.minor = element_blank(),
      axis.text = element_text(size = base_size - 2, color = "gray20"),
      axis.title = element_text(size = base_size, color = "gray10"),
      legend.text = element_text(size = base_size - 2),
      legend.title = element_text(size = base_size - 1, face = "bold"),
      plot.margin = margin(15, 15, 15, 15)
    )
}

# --- FIGURE 1: Map + Histogram ---
cat("  Figure 1...\n")

world <- rnaturalearth::ne_countries(scale = "medium", returnclass = "sf")
mollweide_crs <- "+proj=moll +lon_0=0 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
world_moll <- st_transform(world, mollweide_crs)
site_centroids <- suppressWarnings(
  site_scores_spatial |> st_make_valid() |> st_centroid()
)
centroids_moll <- st_transform(site_centroids, mollweide_crs)

fig1a <- ggplot() +
  geom_sf(data = world_moll, fill = "gray92", color = "gray70", linewidth = 0.15) +
  geom_sf(data = centroids_moll, aes(color = preparedness_score),
          size = 1.2, alpha = 0.75) +
  scale_color_gradientn(
    colors = prep_palette, values = rescale(c(0, 20, 40, 60, 80, 100)),
    limits = c(0, 100), breaks = c(0, 25, 50, 75, 100),
    name = "Regulation\nPreparedness\nIndex",
    guide = guide_colorbar(barwidth = 1.2, barheight = 12, title.position = "top")
  ) +
  labs(tag = "A") +
  theme_pub() +
  theme(axis.text = element_blank(), axis.title = element_blank(),
        panel.grid = element_blank(), legend.position = "right",
        plot.tag = element_text(size = 18, face = "bold"))

fig1b <- ggplot(site_scores, aes(x = preparedness_score)) +
  geom_histogram(aes(fill = after_stat(x)), bins = 25, color = "white", linewidth = 0.3) +
  geom_vline(xintercept = mean_prep, linetype = "dashed", color = "gray30", linewidth = 0.8) +
  annotate("text", x = mean_prep + 2, y = Inf,
           label = paste0("Mean = ", round(mean_prep, 0)),
           hjust = 0, vjust = 2, size = 5, color = "gray30") +
  scale_fill_gradientn(colors = prep_palette, values = rescale(c(0, 20, 40, 60, 80, 100)),
                       limits = c(0, 100), guide = "none") +
  scale_x_continuous(limits = c(0, 100), breaks = seq(0, 100, 25), expand = c(0.01, 0)) +
  scale_y_continuous(expand = c(0, 0, 0.05, 0)) +
  labs(x = "Regulation Preparedness Index", y = "Number of regulatory zones", tag = "B") +
  theme_pub() + theme(plot.tag = element_text(size = 18, face = "bold"))

fig1 <- fig1a / fig1b + plot_layout(heights = c(1.3, 1))
ggsave(file.path(figure_dir, "Figure1_regulation_preparedness.png"), fig1,
       width = 10, height = 11, dpi = 300, bg = "white")
ggsave(file.path(figure_dir, "Figure1_regulation_preparedness.pdf"), fig1,
       width = 10, height = 11, bg = "white")
cat("    Saved\n")

# --- FIGURE 2: Improvement Potential ---
cat("  Figure 2...\n")

fix_summary <- read_csv(file.path(output_dir, "derived/fix_impact_summary.csv"),
                        show_col_types = FALSE)

fix_plot_data <- fix_summary |>
  mutate(
    fix_label = case_when(
      fix_name == "clear_prohibition" ~ "Add clear prohibition",
      fix_name == "remove_discretion" ~ "Remove discretionary language",
      fix_name == "vessel_id" ~ "Add vessel ID requirement",
      fix_name == "evidence_pathway" ~ "Specify evidence pathway",
      fix_name == "temporal_scope" ~ "Clarify temporal scope",
      fix_name == "monitoring_reference" ~ "Reference monitoring technology",
      fix_name == "reporting_requirement" ~ "Add reporting requirements",
      TRUE ~ fix_name
    ),
    fix_label = fct_reorder(fix_label, pct_sites_applicable)
  )

fig2a <- ggplot(fix_plot_data, aes(x = fix_label, y = pct_sites_applicable)) +
  geom_col(aes(fill = impact_per_site), width = 0.7) +
  geom_text(aes(label = paste0(round(pct_sites_applicable, 0), "%")),
            hjust = -0.15, size = 4.5, color = "gray30") +
  scale_fill_gradientn(colors = c("gray85", "#B2DFDB", "#4DB6AC", "#00897B", "#004D40"),
                       limits = c(5, 20), name = "Point\nimprovement",
                       guide = guide_colorbar(barwidth = 1, barheight = 8)) +
  scale_y_continuous(limits = c(0, 100), breaks = seq(0, 100, 25),
                     labels = function(x) paste0(x, "%"), expand = c(0, 0)) +
  coord_flip(clip = "off") +
  labs(x = NULL, y = "Percentage of zones requiring this fix", tag = "A") +
  theme_pub() +
  theme(legend.position = "right", panel.grid.major.y = element_blank(),
        plot.tag = element_text(size = 18, face = "bold"),
        plot.margin = margin(15, 40, 15, 15))

score_comparison <- bind_rows(
  site_scores |> select(site_id, score = preparedness_score) |> mutate(scenario = "Current"),
  site_scores |> select(site_id, score = improved_score) |> mutate(scenario = "After fixes")
) |> mutate(scenario = factor(scenario, levels = c("Current", "After fixes")))

fig2b <- ggplot(score_comparison, aes(x = score, fill = scenario)) +
  geom_density(alpha = 0.65, color = "white", linewidth = 0.5) +
  geom_vline(
    data = score_comparison |> group_by(scenario) |>
      summarise(mean_score = mean(score), .groups = "drop"),
    aes(xintercept = mean_score, color = scenario),
    linetype = "dashed", linewidth = 0.9, show.legend = FALSE
  ) +
  annotate("segment", x = mean_prep, xend = mean_improved, y = 0.035, yend = 0.035,
           arrow = arrow(length = unit(0.25, "cm"), type = "closed"),
           color = "gray30", linewidth = 0.8) +
  annotate("text", x = (mean_prep + mean_improved) / 2, y = 0.04,
           label = paste0("+", round(pct_increase, 0), "% improvement"),
           size = 4.5, fontface = "bold", color = "gray30") +
  scale_fill_manual(values = c("Current" = "#E66101", "After fixes" = "#00897B"), name = NULL) +
  scale_color_manual(values = c("Current" = "#E66101", "After fixes" = "#00897B")) +
  scale_x_continuous(limits = c(0, 100), breaks = seq(0, 100, 25)) +
  labs(x = "Regulation Preparedness Index", y = "Density", tag = "B") +
  theme_pub() +
  theme(legend.position = c(0.15, 0.85),
        legend.background = element_rect(fill = "white", color = NA),
        plot.tag = element_text(size = 18, face = "bold"))

fig2 <- fig2a / fig2b + plot_layout(heights = c(1, 0.8))
ggsave(file.path(figure_dir, "Figure2_improvement_potential.png"), fig2,
       width = 10, height = 10, dpi = 300, bg = "white")
ggsave(file.path(figure_dir, "Figure2_improvement_potential.pdf"), fig2,
       width = 10, height = 10, bg = "white")
cat("    Saved\n")

# --- FIGURE S1: Country boxplot ---
cat("  Figure S1...\n")
figS1 <- ggplot(site_scores, aes(x = reorder(country, preparedness_score, FUN = median),
                                  y = preparedness_score)) +
  geom_boxplot(aes(fill = after_stat(middle)), outlier.size = 0.5, outlier.alpha = 0.3) +
  scale_fill_gradientn(colors = prep_palette, values = rescale(c(0, 20, 40, 60, 80, 100)),
                       limits = c(0, 100), guide = "none") +
  geom_hline(yintercept = mean_prep, linetype = "dashed", color = "gray40", linewidth = 0.7) +
  annotate("text", x = 0.5, y = mean_prep + 3,
           label = paste0("Global mean = ", round(mean_prep, 0)),
           hjust = 0, size = 4, color = "gray40") +
  coord_flip() +
  labs(x = NULL, y = "Regulation Preparedness Index") +
  theme_pub() + theme(panel.grid.major.y = element_blank())

ggsave(file.path(figure_dir, "FigureS1_country_comparison.png"), figS1,
       width = 10, height = 8, dpi = 300, bg = "white")
ggsave(file.path(figure_dir, "FigureS1_country_comparison.pdf"), figS1,
       width = 10, height = 8, bg = "white")
cat("    Saved\n")

# --- FIGURE S2: Enforcement features ---
cat("  Figure S2...\n")

feature_data <- tibble(
  feature = c("Prohibition language", "Vessel reference", "Evidence pathway",
              "Monitoring technology", "Reporting requirement"),
  pct = c(mean(site_scores$has_prohibition) * 100,
          mean(site_scores$has_vessel_reference) * 100,
          mean(site_scores$has_evidence_pathway) * 100,
          mean(site_scores$has_monitoring_reference) * 100,
          mean(site_scores$has_reporting_requirement) * 100)
) |> mutate(feature = fct_reorder(feature, pct))

figS2 <- ggplot(feature_data, aes(x = feature, y = pct)) +
  geom_col(aes(fill = pct), width = 0.7) +
  geom_text(aes(label = paste0(round(pct, 1), "%")), hjust = -0.1, size = 4) +
  scale_fill_gradientn(colors = prep_palette, values = rescale(c(0, 20, 40, 60, 80, 100)),
                       limits = c(0, 100), guide = "none") +
  scale_y_continuous(limits = c(0, 110), expand = c(0, 0)) +
  coord_flip() +
  labs(x = NULL, y = "Percentage of zones containing feature") +
  theme_pub() + theme(panel.grid.major.y = element_blank())

ggsave(file.path(figure_dir, "FigureS2_enforcement_features.png"), figS2,
       width = 10, height = 6, dpi = 300, bg = "white")
ggsave(file.path(figure_dir, "FigureS2_enforcement_features.pdf"), figS2,
       width = 10, height = 6, bg = "white")
cat("    Saved\n")

# ============================================================================
# 4. EXPORT SPATIAL
# ============================================================================

st_write(
  site_scores_spatial |> select(SITE_ID, preparedness_score, improved_score),
  file.path(output_dir, "mpa_scores_spatial.gpkg"),
  delete_dsn = TRUE, quiet = TRUE
)
cat("  Saved mpa_scores_spatial.gpkg\n")

cat("\nDone.\n")
