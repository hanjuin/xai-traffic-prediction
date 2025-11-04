# General
    * [X] ~~*project file created*~~ [2025-09-24]
    * [X] ~~*github sync*~~ [2025-09-24]

# Traffic Prediction
    * [X] ~~*Dataset from AT*~~ [2025-09-24]
    * [X] ~~*Dataset Cleaning*~~ [2025-09-24] 
    * [X] ~~*XGBoost implementation*~~ [2025-09-24]
    * [X] ~~*Automatic outlier detection*~~ [2025-09-24]
    * [X] ~~*remove timestamp that have continuos zero volume*~~ [2025-09-24]
    * [X] ~~*add spatial feature, turning traffic and direction*~~ [2025-09-24]
    
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
    * [X] ~~*Export hotspot to SUMO*~~ [2025-09-30]
    * [X] ~~*Run basic simulation*~~ [2025-10-01]
    * [X] ~~*Extract simulation KPI (Queue Length, Travel Time)*~~ [2025-10-07]

# LLM Policy Creation
    * [X] ~~*Design prompt template*~~ [2025-10-07]
          "Given KPI = [x], context =  [y], SHAP insight = [z], recommend traffic policy
    * [X] ~~*OUTPUT: Policy Recommendations*~~ [2025-10-07]
    * [X] ~~*include XAI result*~~ [2025-10-13]

# Traffic Validation
    * [X] ~~*Implement policy recommendations*~~ [2025-10-07] 
    * [X] ~~*Define Validation Metric*~~ [2025-10-10] 

* [X] ~~*organize source code*~~ [2025-10-09]
    * [X] ~~*traffic simulation result - date indexed*~~ [2025-10-09]
    * [X] ~~*LLM result - date indexed*~~ [2025-10-09]
    * [X] ~~*road network - date indexed*~~ [2025-10-09]
* [X] ~~*create traffic based on most congestion day*~~ [2025-10-10] 
        Average traffic for site 2906: 5692.525229357798
        Most traffic day for site 2906: 2024-10-04 with 15781 vehicles
* [X] ~~*edit LLM prompt - include XAI results*~~ [2025-10-10] 
* [X] ~~*run simulation*~~ [2025-10-10]

* [X] ~~*identified why XAI result make the LLM worse*~~ [2025-10-13]
* [X] ~~*do another LLM focus on traffic timing only (green wave method)*~~ [2025-10-11]