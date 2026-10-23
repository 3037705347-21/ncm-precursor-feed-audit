# NCM 前驱体换型配料复核

共沉淀车间准备把一批回收液和三条新液流配成 NCM 8:1:1 前驱体进料。循环槽里的旧程序只会把四股液体各取四分之一，也没有处理 ICP 前的稀释，因此化验单上的读数会被直接当成原液浓度。换型窗口只剩一个班次，配制组需要一份能够直接排泵、领碱并核对副产物的物料单。

`/workspace` 里已有 `precursor_feed` 包的骨架。请保留包名和公开函数参数，把计算补完整，并提供下面的命令入口：

```bash
python -m precursor_feed.cli STOCKS.csv CAMPAIGN.json PLAN.json
```

`STOCKS.csv` 必须是四行长表，列名固定为：

```text
stream_id,ni_icp_mg_l,co_icp_mg_l,mn_icp_mg_l,iron_icp_mg_l,sample_ml,final_volume_ml,density_kg_l,free_acid_mmol_l
```

`stream_id` 必须恰好包含 `recycle`、`ni_sulfate`、`co_sulfate`、`mn_sulfate`，不得重复或缺失。列顺序可以调整，但缺列和多列都要拒绝。四个 `*_icp_mg_l` 都是取样液定容后上机得到的读数；真实原液质量浓度为读数乘 `final_volume_ml / sample_ml`。`density_kg_l` 和 `free_acid_mmol_l` 已经是原液性质，不再乘稀释倍数。所有数值必须是有限数；取样体积、最终体积和密度必须大于零，最终体积不得小于取样体积；各读数和游离酸不得为负。

`CAMPAIGN.json` 至少包含：

```text
batch_id
target_ratio
target_total_metal_mol_l
batch_feed_m3
stage_fractions
feeding_duration_min
caustic_wt_fraction
caustic_density_kg_l
oh_excess_fraction
max_iron_ppm
max_na2so4_wt_fraction
precipitate_density_kg_l
working_volume_m3
cold_na2so4_solubility_wt_fraction
cake_moisture_kg_per_kg_solid
cake_wash_target_sulfate_wt_fraction
wash_water_budget_kg_per_kg_solid
max_wash_stages
```

`target_ratio` 是含 `ni`、`co`、`mn` 三个键的对象，三个比例均不得为负且和必须大于零。`target_total_metal_mol_l`、`batch_feed_m3`、`feeding_duration_min`、`caustic_density_kg_l`、`max_iron_ppm`、`precipitate_density_kg_l`、`working_volume_m3`、`cake_moisture_kg_per_kg_solid` 和 `wash_water_budget_kg_per_kg_solid` 必须大于零；`caustic_wt_fraction` 和 `max_na2so4_wt_fraction` 必须在 `(0, 1]`；`cold_na2so4_solubility_wt_fraction` 必须在 `(0, 0.4)`；`cake_wash_target_sulfate_wt_fraction` 必须大于零且不得超过冷端溶解度；`max_wash_stages` 必须是 `1` 到 `8` 的整数；`oh_excess_fraction` 不得为负。`stage_fractions` 必须正好三项且都大于零，三项之和与 1 的差不得超过 `1e-9`。

采用以下原子量和摩尔质量，单位均为 g/mol：

```text
Ni                  58.6934
Co                  58.933194
Mn                  54.938044
Fe                  55.845
Ni(OH)2             92.70808
Co(OH)2             92.947874
Mn(OH)2             88.952724
NaOH                39.99711
Na2SO4             142.04214
Na2SO4·10H2O        322.19494
```

原液中某种金属的摩尔浓度按 `reading_mg_l * final_volume_ml / sample_ml / (1000 * atomic_mass)` 计算。混合按体积可加处理，不校正混合收缩。设四股液流的体积分数为 `f_i`，混合液金属摩尔浓度为 `sum(f_i * c_i)`，混合密度为 `sum(f_i * rho_i)`。

混合必须同时满足三个金属的目标浓度和体积分数归一化。记目标总金属浓度为 `C`，目标比例归一化后为 `r_ni, r_co, r_mn`，则三个金属目标浓度分别为 `C*r_ni`、`C*r_co`、`C*r_mn`。请联立四个方程求四条液流的分数，不能只按比例硬分。任一分数的负值超过 `1e-9` 都表示该批不可达；接近零的负值可以截成零。方程接近奇异或残差超过 `1e-9` 时也必须拒绝。

混合液铁含量按质量分数计算：`sum(f_i * iron_mg_l_i) / sum(f_i * density_kg_l_i)`，单位为 ppm，即 mg/kg。超过 `max_iron_ppm` 时整批拒绝。

批次计划以 `batch_feed_m3` 为混合液总体积。各液流体积为 `f_i * batch_feed_m3 * 1000` L，商品液质量为体积乘该液流密度，单位 kg。批次总金属摩尔数为混合总金属浓度乘总体积升数；各金属摩尔数分别按混合浓度乘总体积升数计算。混合游离酸摩尔浓度为分数加权值，再乘总体积升数得到游离酸摩尔数。

三段进料比例使用 `stage_fractions`。每阶段时长为 `feeding_duration_min * stage_fraction` 分钟；该阶段各液流体积等于批次中该液流总体积乘阶段分数；阶段体积流量按该阶段自己的时长换算成 L/h。三个阶段各液流体积之和必须回到批次体积。

沉淀按 `M2+ + 2OH- -> M(OH)2` 计算。游离酸按 H+ 当量计，先与等摩尔 OH- 中和，再对基础碱量乘 `1 + oh_excess_fraction` 作为过程过量。碱液是质量分数为 `caustic_wt_fraction` 的 NaOH 溶液，商业碱液质量由纯 NaOH 质量除以质量分数得到，体积再由质量和 `caustic_density_kg_l` 换算。氢氧化物固体按摩尔数乘各自的 `M(OH)2` 摩尔质量求和。硫酸根来自金属硫酸盐和游离硫酸：每个金属摩尔贡献 1 mol 硫酸根，每 2 mol H+ 当量贡献 1 mol 硫酸根；硫酸钠质量按 142.04214 g/mol 计算。

反应后的液相质量不能直接取进料加碱液。四种金属硫酸盐沉淀为氢氧化物后，固体从液相基准中扣除：`liquid_mass_before_dilution = sum(stock_mass_kg) + caustic_solution_kg - hydroxide_solids_kg`。该值必须大于零。硫酸钠质量分数以液相质量为分母。若它超过 `max_na2so4_wt_fraction`，需要在反应后补入清水，把质量分数恰好稀释到上限；否则补水为零。清水密度按 1 kg/L。补水不影响前面已经结算的进料、沉积和碱耗。

最终工作体积按 `final_slurry_volume_m3 = batch_feed_m3 + caustic_solution_l/1000 + dilution_water_l/1000 + hydroxide_solids_kg/precipitate_density_kg_l/1000` 估算。这个值超过批次允许的 `working_volume_m3` 时整批拒绝。

反应液进入冷却工段后，如果硫酸钠超过 `cold_na2so4_solubility_wt_fraction`，会析出十水硫酸钠。设冷却前液相质量为 `L`、硫酸钠质量为 `S`、冷端溶解度为 `c`、摩尔质量比 `r = 322.19494 / 142.04214`。若 `S/L <= c`，结晶量为零且液相不变。否则设结晶带走的无水硫酸钠为 `x`，满足 `(S-x)/(L-r*x)=c`，按此式求解 `x`。十水硫酸钠质量为 `r*x`，剩余液相质量为 `L-r*x`，剩余硫酸钠质量为 `S-x`。不要只扣硫酸钠而忽略结晶带走的液相水。

结晶后的滤饼进入两级逆流洗涤。每级过滤后，每千克十水硫酸钠干固体都夹带 `cake_moisture_kg_per_kg_solid` kg 液相；一级入口液相为结晶后母液，二级入口为清水，二级出口液相全部进入一级，一级滤液排出。两级的夹带比相同，且假设洗涤过程不溶解十水硫酸钠。求达到 `cake_wash_target_sulfate_wt_fraction` 所需的最小洗水量。洗水只从二级进入。若目标不低于结晶后液相中的硫酸钠质量分数，洗水量为零、各级液相组成不变。

在实际洗水预算为 `wash_water_budget_kg_per_kg_solid * sodium_sulfate_decahydrate_kg` 的前提下，还要从一级开始逐级增加逆流洗涤级数，选择达到同一滤饼目标的最少整数级数。设级数为 `N`，全部洗水只从第 `N` 级进入，第 `i` 级出口自由液相以相同流量进入第 `i-1` 级，每级滤饼夹带量仍为 `E = cake_moisture_kg_per_kg_solid * sodium_sulfate_decahydrate_kg`。一级入口还有全部剩余母液，末级入口为全部清水。对每一级用硫酸钠和液相总量守恒建立稳态方程；从 `N=1` 到 `max_wash_stages` 依次求解，取第一个最终滤饼液相质量分数不大于目标值的方案。若直到上限仍达不到目标，整批拒绝。未达到目标的中间级数不能写入最终结果。

成功输出 JSON 的根对象固定为：

```text
batch_id
stocks
blend_fractions
blend
batch
reaction
conditioning
crystallization
washing
multistage_washing
```

`stocks` 的键是四个液流 ID，每个值包含 `ni_mol_l`、`co_mol_l`、`mn_mol_l`、`iron_mg_l`、`density_kg_l`、`free_acid_mol_l`。`blend_fractions` 的键同样是四个液流 ID。`blend` 包含 `ni_mol_l`、`co_mol_l`、`mn_mol_l`、`total_metal_mol_l`、`iron_ppm`、`density_kg_l`、`free_acid_mol_l`。

`batch` 包含 `feed_m3`、`feed_l`、`total_metal_mol`、`free_acid_mol`、`metal_moles`、`stock_volume_l`、`stock_mass_kg`、`stages`。`metal_moles` 含 `ni`、`co`、`mn`；后两个对象以液流 ID 为键。`stages` 是按顺序排列的三个对象，每个包含 `stage`、`duration_min`、`volumes_l`、`flows_l_h`，后两项均以液流 ID 为键。

`reaction` 包含 `caustic_pure_mol`、`caustic_solution_kg`、`caustic_solution_l`、`hydroxide_solids_kg`、`sodium_sulfate_kg`。

`conditioning` 包含 `feed_mass_kg`、`liquid_mass_before_dilution_kg`、`dilution_water_kg`、`dilution_water_l`、`final_liquid_mass_kg`、`sodium_sulfate_wt_fraction`、`final_slurry_volume_m3`。

`crystallization` 包含 `sodium_sulfate_decahydrate_kg`、`crystallized_sulfate_kg`、`remaining_liquid_kg`、`remaining_sodium_sulfate_kg`、`remaining_sodium_sulfate_wt_fraction`。

`washing` 包含 `dry_solid_kg`、`entrained_liquor_kg`、`wash_water_kg`、`stage1_liquid_sulfate_wt_fraction`、`final_cake_sulfate_kg`、`filtrate_sulfate_kg`、`sulfate_recovery_fraction`、`final_cake_sulfate_wt_fraction`。

`multistage_washing` 包含 `stages`、`dry_solid_kg`、`entrained_liquor_kg_per_stage`、`total_wash_water_kg`、`stage_liquid_sulfate_wt_fractions`、`final_cake_sulfate_kg`、`sulfate_recovery_fraction`、`final_cake_sulfate_wt_fraction`。

下游会直接调用以下入口，请保持参数次序：

```text
precursor_feed.measurements.element_molarity_mol_l(
    reading_mg_l, sample_ml, final_volume_ml, atomic_mass_g_mol
)
precursor_feed.measurements.iron_mass_concentration_mg_l(
    reading_mg_l, sample_ml, final_volume_ml
)
precursor_feed.measurements.normalize_stocks(raw_stocks)
precursor_feed.blending.solve_blend(
    stocks, target_ratio, target_total_metal_mol_l
)
precursor_feed.charging.batch_plan(
    batch_feed_m3, stage_fractions, feeding_duration_min,
    fractions, stocks, blend
)
precursor_feed.stoichiometry.reaction_plan(
    metal_moles, free_acid_mol, oh_excess_fraction,
    caustic_wt_fraction, caustic_density_kg_l
)
precursor_feed.conditioning.conditioning_plan(
    batch, reaction, max_na2so4_wt_fraction,
    precipitate_density_kg_l, working_volume_m3
)
precursor_feed.crystallization.crystallization_plan(
    conditioning, cold_na2so4_solubility_wt_fraction
)
precursor_feed.washing.washing_plan(
    crystallization, cake_moisture_kg_per_kg_solid,
    cake_wash_target_sulfate_wt_fraction
)
precursor_feed.multistage_washing.multistage_washing_plan(
    crystallization, cake_moisture_kg_per_kg_solid,
    cake_wash_target_sulfate_wt_fraction,
    wash_water_budget_kg_per_kg_solid, max_wash_stages
)
```

`normalize_stocks` 接收 CSV 解析后的四行字典列表，返回以液流 ID 为键的归一化对象。`solve_blend` 返回 `{"fractions": ..., "blend": ...}`。`batch_plan` 返回 `batch` 段，`reaction_plan` 返回 `reaction` 段，`conditioning_plan` 返回 `conditioning` 段，`crystallization_plan` 返回 `crystallization` 段，`washing_plan` 返回 `washing` 段，`multistage_washing_plan` 返回 `multistage_washing` 段。所有非法数值或不可行约束都应抛出 `ValueError`。

目标文件只能在全部计算和铁限值检查完成后写入。成功时先在同目录写临时文件，再用原子替换落到 `PLAN.json`；输入不合法、混合不可达、铁超限或计算失败时，命令应以非零状态退出、把原因写到标准错误，并且不得创建或覆盖目标文件。

`/workspace/data/stocks.csv` 和 `/workspace/data/campaign.json` 是按固定种子生成的模拟记录，用于核对接口和输出结构，不是车间原始台账。
