window.showToast = showToast;
window.initPage = initPage;
window.queueToast = queueToast;
window.userRoles = userRoles;
window.isAdminUser = isAdminUser;
window.isReadOnlyUser = isReadOnlyUser;
window.ROLE_VIEW_ROLES = ROLE_VIEW_ROLES;
window.ROLE_VIEW_LEVELS = ROLE_VIEW_LEVELS;
window.ROLE_VIEW_IDS = ROLE_VIEW_IDS;
window.SIDEBAR_DEFAULT_LAYOUT = SIDEBAR_DEFAULT_LAYOUT;
window.roleViewDefaultAccess = roleViewDefaultAccess;
window.normalizeViewId = normalizeViewId;
window.normalizeRoleViewAccess = normalizeRoleViewAccess;
window.cacheRoleViewAccess = cacheRoleViewAccess;
window.roleViewAccessPayload = roleViewAccessPayload;
window.canViewPage = canViewPage;
window.canEditPage = canEditPage;
window.canEditPlanning = canEditPlanning;
window.canViewPlanning = canViewPlanning;
window.canUseAllocationTools = canUseAllocationTools;
window.canUseAllocationProcess = canUseAllocationProcess;
window.readAreaFocus = readAreaFocus;
window.writeAreaFocus = writeAreaFocus;
window.areaFocusCode = areaFocusCode;
window.areaFocusAreaId = areaFocusAreaId;
window.areaFocusName = areaFocusName;
window.setAreaFocusAreas = setAreaFocusAreas;
window.preferredAreaIdFromFocus = preferredAreaIdFromFocus;
window.compareActivitiesForAreaFocus = compareActivitiesForAreaFocus;
window.comparePersonsForAreaFocus = comparePersonsForAreaFocus;
window.setupSyncedHorizontalScroll = setupSyncedHorizontalScroll;
window.setupClientSortableTables = setupClientSortableTables;
window.setupImportHelpButton = setupImportHelpButton;
window.openBulkImportGrid = openBulkImportGrid;
window.appendAppLog = appendAppLog;
window.clearAppLog = clearAppLog;
window.flowRecordWaitMetric = recordWaitMetric;
window.flowFlushWaitMetrics = flushWaitMetrics;
window.flowTrack = flowTrack;
window.flowFlushInteractions = flushInteractions;
window.flowCurrentInteractionContext = currentInteractionContext;
window.flowLog = {
  append: appendAppLog,
  info: (message, title = "Info") => appendAppLog(message, "info", title),
  success: (message, title = "Klart") => appendAppLog(message, "success", title),
  warn: (message, title = "Varning") => appendAppLog(message, "warn", title),
  error: (message, title = "Fel") => appendAppLog(message, "error", title),
  clear: clearAppLog,
};
window.clearAllUploadedFiles = clearAllUploadedFiles;
window.sharedAllocationUploads = {
  saveFiles: saveSharedAllocationFiles,
  clearGeneration: sharedAllocationClearGeneration,
};
window.flowBackgroundPrefetch = {
  status: backgroundPrefetchStatus,
  waitForIdle: waitForBackgroundPrefetchIdle,
};
window.allocationUploadActivity = {
  start: startAllocationUploadActivity,
  finish: finishAllocationUploadActivity,
  clear: clearAllocationUploadNotice,
};
window.readSelectedDate = readSelectedDate;
window.writeSelectedDate = writeSelectedDate;
window.clearSelectedDate = clearSelectedDate;
