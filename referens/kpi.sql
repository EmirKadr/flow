    ["OUTBOUND_Manual_Pick_Rows"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'A' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts e-commerce order rows from zone E
    ["OUTBOUND_E_Commerce_Rows"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'E' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts chair zone order rows from zone G
    ["OUTBOUND_Chair_Zone_Rows"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'G' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts bulky item order rows from zone S
    ["OUTBOUND_Bulky_Pick_Rows"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'S' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts Marble item order rows from zone Q
    ["OUTBOUND_Marble_Rows"] = $$"""
         SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
         FROM PICK_LOG
         WHERE [PICK_ZONE] = 'Q' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
         """,

    // Counts autostore order rows from zone R
    ["OUTBOUND_Autostore_Rows"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'R' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts outdoor furniture order rows from zone U (HFN)
    ["OUTBOUND_Outdoor_Furniture_Rows"] = $$"""
         SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
         FROM PICK_LOG
         WHERE [PICK_ZONE] = 'U' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
         """,

    // Counts small pick order rows from zone Z (HFN)
    ["OUTBOUND_Small_Pick_Rows"] = $$"""
         SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
         FROM PICK_LOG
         WHERE [PICK_ZONE] = 'Z' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
         """,

    // Counts flammable pick order rows from zone F (Frey)
    ["OUTBOUND_Flammable_Rows"] = $$"""
         SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
         FROM PICK_LOG
         WHERE [PICK_ZONE] = 'F' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
         """,

    // Sums the total number of packages manually picked from zone A
    ["OUTBOUND_Manual_Pick_Package"] = $$"""
        SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'A' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Sums the total number of e-commerce packages from zone E
    ["OUTBOUND_E_Commerce_Package"] = $$"""
        SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'E' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Sums the total number of chair zone packages from zone G
    ["OUTBOUND_Chair_Zone_Package"] = $$"""
        SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'G' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Sums the total number of marble packages from zone Q
    ["OUTBOUND_Marble_Package"] = $$"""
        SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'Q' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Sums the total number of bulky packages from zone S
    ["OUTBOUND_Bulky_Pick_Package"] = $$"""
        SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'S' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Sums the total number of autostore packages from zone R
    ["OUTBOUND_Autostore_Package"] = $$"""
        SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'R' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Sums the total number of outdoor furniture packages from zone U (HFN)
    ["OUTBOUND_Outdoor_Furniture_Package"] = $$"""
        SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'U' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Sums the total number of small packages from zone Z (HFN)
    ["OUTBOUND_Small_Pick_Package"] = $$"""
        SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'Z' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Sums the total number of flammable packages from zone F (FREY)
    ["OUTBOUND_Flammable_Package"] = $$"""
        SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'F' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts full pallets picked from high bay warehouse (HBW) from UT locations
    ["OUTBOUND_Full_Pallet_From_HBW_Pallets"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'H' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum
        AND LOCATION LIKE 'UT%' AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts full pallets picked from manual buffer locations
    ["OUTBOUND_Full_Manual_Buffer_Pallets"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'H' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum
        AND LOCATION NOT LIKE 'UT%' AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts total amount of pallets sorted to Ecom by SGA
    ["OUTBOUND_Sort_Ecom_Pallets"] = $$"""
       SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
       FROM SORT_CONVEYOR_LOG
       WHERE LEN([SSCC]) < 12
       AND [SHIPMENT_ID] LIKE @company + '-' + @warehNum + '-%'
       AND CAST(TIMESTAMP AS DATE) = @date
      """,

    // Counts total amount of pallets sorted to store by SGA
    ["OUTBOUND_Sort_Store_Pallets"] = $$"""
       SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
       FROM SORT_CONVEYOR_LOG
       WHERE LEN([SSCC]) >= 12
       AND [SHIPMENT_ID] LIKE @company + '-' + @warehNum + '-%'
       AND CAST(TIMESTAMP AS DATE) = @date
       """,

    // Counts the total amount of packing pallets
    ["OUTBOUND_Ecom_Pack_Pallets"] = $$"""
        SELECT DISTINCT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM LOADING_LOG
        WHERE [TYPE] = 220 AND COMPANY = @company
        AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // =============
    // INTERNAL
    // =============

    ["INTERNT_Refill_AS_VM_Rows"] = string.Empty,
    ["INTERNT_Refill_AS_Buffer_Rows"] = string.Empty,
    ["INTERNT_Manual_Rack_Rows"] = string.Empty,
    ["INTERNT_Manual_HBW_Rows"] = string.Empty,

    // Counts refill pallets moved from HBW (AA locations or Transit) to picking locations
    ["INTERNT_Refill_Manual_HBW_Pallets"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM TRANS_LOG
        WHERE [TYPE] IN (31, 51) AND COMPANY = @company AND [WAREH_NUM] = @warehNum
        AND (LOC_FROM LIKE 'AA%' OR LOC_FROM = 'Transit' OR LOC_FROM LIKE 'UT%')
        AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts refill pallets moved from manual rack (not from AA or Transit) to picking locations
    ["INTERNT_Refill_Manual_Rack_Pallets"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM TRANS_LOG
        WHERE [TYPE] = 31 AND COMPANY = @company AND [WAREH_NUM] = @warehNum
        AND LOC_FROM NOT LIKE 'AA%' ANd LOC_FROM != 'Transit' AND LOC_FROM NOT LIKE 'UT%'
        AND CAST(TIMESTAMP AS DATE) = @date
        """,

    ["INTERNT_Refill_Manual_Rack_Pallets_TM"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM TRANS_LOG
        WHERE [TYPE]  IN (51, 54) AND COMPANY = @company AND [WAREH_NUM] = @warehNum
        AND LOC_FROM NOT LIKE 'INL%'
        AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Count total pallets that has been buffer updated (Frey)
    ["INTERNT_Buffer_Update_Pallets"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM RECEIVE_LOG
        WHERE [TYPE] = 91 AND COMPANY = @company AND [WAREH_NUM] = @warehNum
        AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts the total of orders that has been notified for shipping (Frey)
    //["INTERNT_Notification_Orders"] = $$"""
    //      SELECT COUNT(DISTINCT o.SHIPMENT_ID) AS 'KpiValue', {{CommonColumns}}
    //      FROM BASE_PALLET_LOG bp
    //      INNER JOIN ORDER_LOG o ON bp.ORDER_NUM = o.ORDER_NUM AND bp.COMPANY = o.COMPANY
    //      WHERE bp.COMPANY = @company
    //      AND CAST(bp.TIMESTAMP AS DATE) = @date
    //      """,

    // =============
    // INBOUND
    // =============

    // Sums the quantity of packages moved during decanting to autostore locations
    ["INBOUND_Decanting_Package"] = $$"""
        SELECT SUM(QTY) AS 'KpiValue', {{CommonColumns}}
        FROM TRANS_LOG
        WHERE [TYPE] = 26 AND COMPANY = @company AND [WAREH_NUM] = @warehNum
        AND LOC_TO LIKE 'AS%' AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts the number of rows (compartments) moved during decanting to autostore locations
    ["INBOUND_Decanting_Rows"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM TRANS_LOG
        WHERE [TYPE] = 26 AND COMPANY = @company AND [WAREH_NUM] = @warehNum
        AND LOC_TO LIKE 'AS%' AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts unique pallets moved to high bay warehouse (HBW) locations
    ["INBOUND_HBW_Pallets"] = $$"""
        SELECT COUNT(DISTINCT PALL_NUM) AS 'KpiValue', {{CommonColumns}}
        FROM TRANS_LOG
        WHERE [TYPE] = 111 AND COMPANY = @company AND [WAREH_NUM] = @warehNum
        AND LOC_TO LIKE 'HBW%' AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts pallets moved to manual buffer locations, excluding pallets with status 66 (new pallet created)
    ["INBOUND_Manual_Buffer_Pallets"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM TRANS_LOG
        WHERE [TYPE] = 22 AND COMPANY = @company AND [WAREH_NUM] = @warehNum
        AND CAST(TIMESTAMP AS DATE) = @date
        AND PALL_NUM NOT IN (
            SELECT PALL_NUM FROM TRANS_LOG
            WHERE TYPE = 66
        )
        """,

    // Counts rows moved from VM to picking locations
    ["INBOUND_Putaway_Pick_Pallets"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM TRANS_LOG
        WHERE [TYPE] IN (21, 27, 29) AND COMPANY = @company AND [WAREH_NUM] = @warehNum
        AND CAST(TIMESTAMP AS DATE) = @date
        """,

    ["INBOUND_Putaway_Pick_Pallets"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM TRANS_LOG
        WHERE [TYPE] IN (21, 27, 29) AND COMPANY = @company AND [WAREH_NUM] = @warehNum
        AND LOC_TO NOT LIKE 'VM&'
        AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts received order rows excluding returns, zero values, negative values, and re-receipts
    ["INBOUND_Receiving_Rows"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM [dbo].[RECEIVE_LOG]
        WHERE [TYPE] IN (11,12,61,62,71) AND STATUS IN (20, 30)
        AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    ["INBOUND_Returns_Package"] = string.Empty,
    ["INBOUND_Returns_Rows"] = string.Empty
};

/// <summary>
/// Example of keys override per company/warehouse: OUTBOUND_Autostore_Rows, OUTBOUND_Autostore_Rows_GG, OUTBOUND_Autostore_Rows_GG_404
/// </summary>
internal static readonly Dictionary<string, string> OverrideQueries = new(StringComparer.OrdinalIgnoreCase)
{
    // OUTBOUND
    // MG-specific: Counts manually picked order rows from zones M and N changed zone to A, not used anymore
    //["OUTBOUND_Manual_Pick_Rows_MG"] = $$"""
    //    SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
    //    FROM PICK_LOG
    //    WHERE [PICK_ZONE] IN ('M', 'N') AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
    //    """,

    // MG-specific: Counts e-commerce order rows from zone Q
    ["OUTBOUND_E_Commerce_Rows_MG"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'Q' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // MG-specific: Counts bulky item order rows from zone O
    ["OUTBOUND_Bulky_Pick_Rows_MG"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'O' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // GG-specific: Counts campaign order rows from zone K
    ["OUTBOUND_Campaign_Rows_GG"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'K' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // GG-specific: Counts splitorder rows from zone B
    ["OUTBOUND_Order_Split_Rows_GG"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'B' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    //// MG-specific: Sums the total number of packages manually picked from zones M and N not used anymore
    //["OUTBOUND_Manual_Pick_Package_MG"] = $$"""
    //    SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
    //    FROM PICK_LOG
    //    WHERE [PICK_ZONE] IN ('M', 'N') AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
    //    """,

    // GG - specific: Sums the total number of packages manually picked from zones B
    ["OUTBOUND_Order_Split_Packages_GG"] = $$"""
        SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] IN ('B') AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // GG - specific: Sums the total number of packages manually picked from zones K
    ["OUTBOUND_Campaign_Packages_GG"] = $$"""
        SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] IN ('K') AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // MG-specific: Sums the total number of e-commerce packages from zone Q
    ["OUTBOUND_E_Commerce_Package_MG"] = $$"""
        SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'Q' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // MG-specific: Sums the total number of bulky packages from zone O
    ["OUTBOUND_Bulky_Pick_Package_MG"] = $$"""
        SELECT SUM(QTY_SUF) AS 'KpiValue', {{CommonColumns}}
        FROM PICK_LOG
        WHERE [PICK_ZONE] = 'O' AND QTY_SUF > 0 AND COMPANY = @company AND [WAREH_NUM] = @warehNum AND CAST(TIMESTAMP AS DATE) = @date
        """,

    // Counts pallets moved to manual buffer locations, excluding pallets with status 66 (new pallet created) (HFN query)
    ["INBOUND_Manual_Buffer_Pallets_TM"] = $$"""
        SELECT COUNT(*) AS 'KpiValue', {{CommonColumns}}
        FROM [TRANS_LOG] AS tl
        WHERE tl.[TYPE] IN (22, 52)
        AND tl.COMPANY = @company
        AND tl.[WAREH_NUM] = @warehNum
        AND CAST(tl.[TIMESTAMP] AS DATE) = @date
        AND (
            (tl.[TYPE] = 22
            AND tl.[LOC_FROM] IN ('FM', 'T')
            AND tl.[LOC_TO] NOT LIKE 'VM%'
            AND tl.[LOC_TO] NOT LIKE 'INL%')
            OR
            (tl.[TYPE] = 52
            AND tl.[LOC_FROM] LIKE 'VM%')
              )
            AND tl.[PALL_NUM] NOT IN (
              SELECT [PALL_NUM]
              FROM TRANS_LOG
              WHERE [TYPE] = 66
                );
        """,
