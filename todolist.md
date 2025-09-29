# General
    * [X] ~~*project file created*~~ [2025-09-24]
    * [X] ~~*github sync*~~ [2025-09-24]

# Traffic Prediction
    * [X] ~~*Dataset from AT*~~ [2025-09-24]
    * [X] ~~*Dataset Cleaning*~~ [2025-09-24] 
    * [X] ~~*XGBoost implementation*~~ [2025-09-24]
    * [X] ~~*Automatic outlier detection*~~ [2025-09-24]
    * [X] ~~*remove timestamp that have continuos zero volume*~~ [2025-09-24]
    * [X] ~~*add spatial feature, turning traffic and direction (some detector do not have png for references)*~~ [2025-09-24]
    
# XAI Implementation (SHAP)
    * [X] ~~*SHAP Implementation*~~ [2025-09-24]

# Hotspot Detection
    * [X] ~~*KPI Table - rank sites by congestion severity*~~ [2025-09-29]
      * [X] ~~*site level*~~ [2025-09-29] 
        - Rank site by site-level 95th percentile utilization
        - For the top K sites, build lane level table to see which lanes drive the problem
      * [X] ~~*lane level (for policy design)*~~ [2025-09-29]
    * [ ] SHAP plot - explain why those sites congest
    * [X] ~~*Visualize hotspots on a map/diagram*~~ [2025-09-29]
    * [ ] Automate peak-hour vs off-peak comparison
    * [X] ~~*Select top 3 most congestion site for LLM input*~~ [2025-09-29]

# Simulation (Optional)
    * [ ] Export hotspot to SUMO
    * [ ] Run basic simulation
    * [ ] Extract simulation KPI (Queue Length, Travel Time)

# LLM Policy Creation
    * [ ] Design prompt template
          "Given KPI = [x], context =  [y], SHAP insight = [z], recommend traffic policy
    * [ ] OUTPUT: Policy Recommendations

# Traffic Validation
    * [ ] Replicate the top 3 most congestion sites, with sensor
    * [ ] Implement policy recommendations 
    * [ ] Define Validation Metric 
    * [ ] Validate the policy