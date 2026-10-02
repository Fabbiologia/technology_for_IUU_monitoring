#!/usr/bin/env Rscript
# ==============================================================================
# Legislation Readiness Figures
# ==============================================================================
#
# PREREQUISITE: Run python3 analysis/scripts/nlp_contextual_scoring.py first.
#
# INPUT:
#   outputs/latest/legislation_country_scores.csv
#   outputs/latest/regulation_scores.csv
#
# OUTPUT:
#   Figure 3: Legislation readiness + enforcement chain (combined panel)
#   Figure S3: Legislative temporal coverage
#
# ==============================================================================

library(tidyverse)
library(patchwork)
library(scales)

root_dir <- "/Volumes/bacdrive/Dropbox/Work/technology_for_IUU_monitoring"
output_dir <- file.path(root_dir, "outputs/latest")
figure_dir <- file.path(output_dir, "figures")
dir.create(figure_dir, showWarnings = FALSE, recursive = TRUE)

# ==============================================================================
# Load data
# ==============================================================================

leg_path <- file.path(output_dir, "legislation_country_scores.csv")
reg_path <- file.path(output_dir, "regulation_scores.csv")

if (!file.exists(leg_path)) {
  stop("Legislation scores not found. Run: python3 analysis/scripts/nlp_contextual_scoring.py")
}

leg_data <- read_csv(leg_path, show_col_types = FALSE)
reg_data <- read_csv(reg_path, show_col_types = FALSE)

cat("Countries with data:", nrow(leg_data), "\n")
cat("Mean legislation score:", round(mean(leg_data$total_score), 1), "\n")

# ==============================================================================
# Figure 3A: Legislation readiness by dimension (stacked bar)
# ==============================================================================

dim_colors <- c(
  "Evidence" = "#4575B4",
  "Penalty" = "#D73027",
  "Enforcement" = "#F46D43",
  "Technology" = "#74ADD1",
  "Liability" = "#8E44AD"
)

leg_long <- leg_data %>%
  select(country, evidence_score, penalty_score, enforcement_score,
         technology_score, liability_score, total_score) %>%
  pivot_longer(cols = ends_with("_score") & !total_score,
               names_to = "dimension", values_to = "score") %>%
  mutate(
    dimension = case_when(
      dimension == "evidence_score" ~ "Evidence",
      dimension == "penalty_score" ~ "Penalty",
      dimension == "enforcement_score" ~ "Enforcement",
      dimension == "technology_score" ~ "Technology",
      dimension == "liability_score" ~ "Liability"
    ),
    dimension = factor(dimension,
                       levels = c("Evidence", "Penalty", "Enforcement",
                                  "Technology", "Liability")),
    country = fct_reorder(country, score, .fun = sum)
  )

fig3a <- ggplot(leg_long, aes(x = country, y = score, fill = dimension)) +
  geom_col(width = 0.7) +
  scale_fill_manual(values = dim_colors, name = "Dimension") +
  scale_y_continuous(expand = c(0, 0, 0.05, 0)) +
  coord_flip() +
  labs(x = NULL, y = "Legislation Readiness Score", tag = "A") +
  theme_minimal(base_size = 16) +
  theme(
    panel.grid.major.y = element_blank(),
    panel.grid.minor = element_blank(),
    plot.background = element_rect(fill = "white", color = NA),
    plot.tag = element_text(size = 20, face = "bold"),
    legend.position = "bottom",
    legend.title = element_text(face = "bold"),
    axis.text = element_text(size = 14),
    axis.title = element_text(size = 15),
    legend.text = element_text(size = 13)
  )

# ==============================================================================
# Figure 3B: Enforcement chain paired bar
# ==============================================================================

# Country-level mean regulation scores
reg_country <- reg_data %>%
  group_by(country) %>%
  summarise(mean_reg_score = mean(preparedness_score, na.rm = TRUE),
            .groups = "drop")

# Merge with legislation
chain_data <- leg_data %>%
  left_join(reg_country, by = "country") %>%
  mutate(
    leg_score = total_score,
    combined = mean_reg_score + leg_score,
    gap = abs(leg_score - mean_reg_score)
  ) %>%
  arrange(desc(combined))

cat("\nENFORCEMENT CHAIN SUMMARY:\n")
print(chain_data %>% select(country, mean_reg_score, leg_score, combined, gap))

chain_long <- chain_data %>%
  select(country, `Regulation Preparedness (MPA regulations)` = mean_reg_score,
         `Legislation Readiness (national legislation)` = leg_score) %>%
  pivot_longer(-country, names_to = "index", values_to = "score") %>%
  mutate(country = fct_reorder(country, score, .fun = sum))

chain_colors <- c(
  "Regulation Preparedness (MPA regulations)" = "#4575B4",
  "Legislation Readiness (national legislation)" = "#D73027"
)

fig3b <- ggplot(chain_long, aes(x = country, y = score, fill = index)) +
  geom_col(position = position_dodge(width = 0.7), width = 0.65) +
  scale_fill_manual(values = chain_colors, name = NULL,
                    guide = guide_legend(nrow = 2, byrow = TRUE)) +
  scale_y_continuous(limits = c(0, 100), breaks = seq(0, 100, 25),
                     expand = c(0, 0)) +
  coord_flip() +
  labs(x = NULL, y = "Score (0-100)", tag = "B") +
  theme_minimal(base_size = 16) +
  theme(
    panel.grid.major.y = element_blank(),
    panel.grid.minor = element_blank(),
    plot.background = element_rect(fill = "white", color = NA),
    plot.tag = element_text(size = 20, face = "bold"),
    legend.position = "bottom",
    legend.title = element_blank(),
    axis.text = element_text(size = 14),
    axis.title = element_text(size = 15),
    legend.text = element_text(size = 13)
  )

fig3 <- fig3a + fig3b
ggsave(file.path(figure_dir, "Figure3_legislation_enforcement.png"),
       fig3, width = 13, height = 8.5, dpi = 300, bg = "white")
ggsave(file.path(figure_dir, "Figure3_legislation_enforcement.pdf"),
       fig3, width = 13, height = 8.5, bg = "white")
cat("Saved Figure 3 (combined panel)\n")

# ==============================================================================
# Figure S3: Legislative temporal coverage
# ==============================================================================

faolex_meta <- file.path(root_dir, "data/03_external/legislation/legislation_extracted_metadata.csv")
if (file.exists(faolex_meta)) {
  meta <- read_csv(faolex_meta, show_col_types = FALSE)

  COUNTRY_NAMES <- setNames(
    c("Australia", "Canada", "Chile", "Ecuador", "Gabon", "Greece",
      "Indonesia", "Italy", "Malaysia", "Mexico", "New Zealand",
      "Panama", "Republic of Maldives", "South Africa", "Spain"),
    c("AUS", "CAN", "CHL", "ECU", "GAB", "GRC", "IDN", "ITA",
      "MYS", "MEX", "NZL", "PAN", "MDV", "ZAF", "ESP")
  )

  # Use 'year' for original date and 'last_amended' for most recent update
  # Handle cases where year > last_amended (extraction artifacts) using pmin/pmax
  age_data <- meta %>%
    mutate(iso3 = toupper(iso3)) %>%
    filter(iso3 %in% names(COUNTRY_NAMES)) %>%
    mutate(
      country = COUNTRY_NAMES[iso3],
      year = as.numeric(year),
      last_amended = as.numeric(last_amended),
      # Robust: earliest of either field, latest of either field
      yr_min = pmin(year, last_amended, na.rm = TRUE),
      yr_max = pmax(year, last_amended, na.rm = TRUE)
    ) %>%
    filter(!is.na(country), !is.na(yr_min) | !is.na(yr_max)) %>%
    group_by(country) %>%
    summarise(
      oldest = min(yr_min, na.rm = TRUE),
      newest = max(yr_max, na.rm = TRUE),
      n_docs = n(),
      .groups = "drop"
    ) %>%
    filter(is.finite(oldest), is.finite(newest)) %>%
    mutate(country = fct_reorder(country, newest))

  figS3 <- ggplot(age_data, aes(y = country)) +
    geom_segment(aes(x = oldest, xend = newest, yend = country),
                 color = "gray60", linewidth = 1.5) +
    geom_point(aes(x = oldest), color = "#D73027", size = 3.5) +
    geom_point(aes(x = newest), color = "#4DAF4A", size = 3.5) +
    scale_x_continuous(
      breaks = seq(1960, 2026, 5),
      limits = c(NA, 2026)
    ) +
    labs(x = "Year", y = NULL) +
    theme_minimal(base_size = 16) +
    theme(
      panel.grid.major.y = element_blank(),
      panel.grid.minor = element_blank(),
      plot.background = element_rect(fill = "white", color = NA),
      axis.text.x = element_text(angle = 90, hjust = 1, vjust = 0.5, size = 13),
      axis.text.y = element_text(size = 14),
      axis.title = element_text(size = 15)
    )

  ggsave(file.path(figure_dir, "FigureS3_legislative_age.png"),
         figS3, width = 10, height = 7, dpi = 300, bg = "white")
  ggsave(file.path(figure_dir, "FigureS3_legislative_age.pdf"),
         figS3, width = 10, height = 7, bg = "white")
  cat("Saved Figure S3\n")
} else {
  cat("No FAOLEX metadata — skipping Figure S3\n")
}

# ==============================================================================
# Figure S4: Legislation score vs amendment recency (no correlation)
# ==============================================================================

# Use the same metadata for amendment dates
if (exists("age_data") && exists("leg_data")) {

  # Get newest amendment per country from metadata
  newest_amend <- meta %>%
    mutate(
      iso3 = toupper(iso3),
      year = as.numeric(year),
      last_amended = as.numeric(last_amended),
      yr_max = pmax(year, last_amended, na.rm = TRUE)
    ) %>%
    filter(iso3 %in% names(COUNTRY_NAMES), !is.na(yr_max)) %>%
    group_by(iso3) %>%
    summarise(newest_amendment = max(yr_max, na.rm = TRUE), .groups = "drop")

  # Merge with legislation scores
  corr_data <- leg_data %>%
    left_join(newest_amend, by = "iso3") %>%
    filter(!is.na(newest_amendment))

  # Compute correlations
  ct <- cor.test(corr_data$total_score, corr_data$newest_amendment, method = "pearson")
  cs <- cor.test(corr_data$total_score, corr_data$newest_amendment, method = "spearman")

  label_text <- sprintf("Pearson r = %.2f, p = %.3f\nSpearman rho = %.2f, p = %.3f",
                        ct$estimate, ct$p.value, cs$estimate, cs$p.value)

  figS4 <- ggplot(corr_data, aes(x = newest_amendment, y = total_score)) +
    geom_point(size = 4, color = "#4575B4", alpha = 0.8) +
    ggrepel::geom_text_repel(aes(label = country), size = 4.5, max.overlaps = 15,
                              seed = 42, color = "gray30") +
    geom_smooth(method = "lm", se = TRUE, color = "#D73027", linewidth = 0.8,
                linetype = "dashed", alpha = 0.15) +
    annotate("text", x = min(corr_data$newest_amendment) + 2,
             y = max(corr_data$total_score) - 2,
             label = label_text, hjust = 0, size = 5, color = "gray30") +
    scale_x_continuous(breaks = seq(1995, 2025, 5)) +
    labs(
      x = "Year of most recent legislative amendment",
      y = "Legislation Readiness Score (0-100)"
    ) +
    theme_minimal(base_size = 16) +
    theme(
      plot.background = element_rect(fill = "white", color = NA),
      panel.grid.minor = element_blank(),
      axis.text = element_text(size = 14),
      axis.title = element_text(size = 15)
    )

  ggsave(file.path(figure_dir, "FigureS4_score_vs_recency.png"),
         figS4, width = 8, height = 6, dpi = 300, bg = "white")
  ggsave(file.path(figure_dir, "FigureS4_score_vs_recency.pdf"),
         figS4, width = 8, height = 6, bg = "white")
  cat("Saved Figure S4\n")
  cat(sprintf("  Pearson r = %.3f, p = %.4f\n", ct$estimate, ct$p.value))
  cat(sprintf("  Spearman rho = %.3f, p = %.4f\n", cs$estimate, cs$p.value))
} else {
  cat("No metadata or legislation data — skipping Figure S4\n")
}

cat("\nDone! All legislation figures generated.\n")
