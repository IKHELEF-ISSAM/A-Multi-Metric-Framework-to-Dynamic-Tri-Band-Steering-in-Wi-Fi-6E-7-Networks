import { API_BASE_URL } from "../../api";

import React, {
    useCallback,
    useEffect,
    useMemo,
    useState,
} from "react";

import {
    Alert,
    Box,
    Button,
    Card,
    CardContent,
    Chip,
    CircularProgress,
    Divider,
    Grid,
    LinearProgress,
    Paper,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";

import {
    CheckCircle,
    ErrorOutline,
    Memory,
    PlayArrow,
    Radio,
    Refresh,
    Speed,
    Stop,
    Timeline,
    TrendingUp,
    WarningAmber,
    Wifi,
} from "@mui/icons-material";

import Header from "../../components/Header";

// ============================================================================
// API
// ============================================================================

const API_URL =
    API_BASE_URL;

const POLL_INTERVAL = 1000;

// ============================================================================
// CONSTANTS
// ============================================================================

const BANDS = [
    {
        key: "2G",
        label: "2.4 GHz",
    },
    {
        key: "5G",
        label: "5 GHz",
    },
    {
        key: "6G",
        label: "6 GHz",
    },
];

const BAND_LABELS = {
    "2G": "2.4 GHz",
    "5G": "5 GHz",
    "6G": "6 GHz",
};

// ============================================================================
// HELPERS
// ============================================================================

function formatNumber(value, digits = 1) {
    if (
        value === null ||
        value === undefined ||
        Number.isNaN(Number(value))
    ) {
        return "—";
    }

    return Number(value).toFixed(digits);
}

function formatScore(value) {
    if (
        value === null ||
        value === undefined ||
        Number.isNaN(Number(value))
    ) {
        return "—";
    }

    return Number(value).toFixed(1);
}

function formatPercent(value) {
    if (
        value === null ||
        value === undefined ||
        Number.isNaN(Number(value))
    ) {
        return "—";
    }

    return `${Number(value).toFixed(1)}%`;
}

function formatMbps(value) {
    if (
        value === null ||
        value === undefined ||
        Number.isNaN(Number(value))
    ) {
        return "—";
    }

    return `${Number(value).toFixed(2)} Mbps`;
}

function formatTimestamp(timestamp) {
    if (!timestamp) {
        return "—";
    }

    const numeric = Number(timestamp);

    if (!Number.isFinite(numeric)) {
        return "—";
    }

    const date = new Date(numeric * 1000);

    if (Number.isNaN(date.getTime())) {
        return "—";
    }

    return date.toLocaleString();
}

function secondsSince(timestamp) {
    if (!timestamp) {
        return null;
    }

    const numeric = Number(timestamp);

    if (!Number.isFinite(numeric)) {
        return null;
    }

    return Math.max(
        0,
        Date.now() / 1000 - numeric,
    );
}

function formatAge(timestamp) {
    const age = secondsSince(timestamp);

    if (age === null) {
        return "—";
    }

    if (age < 1) {
        return "just now";
    }

    if (age < 60) {
        return `${Math.floor(age)}s ago`;
    }

    if (age < 3600) {
        return `${Math.floor(age / 60)}m ago`;
    }

    return `${Math.floor(age / 3600)}h ago`;
}

function normalizeDecision(device) {
    const decision = String(
        device?.decision || "",
    ).toLowerCase();

    if (
        device?.switched === true ||
        decision === "switch" ||
        decision === "steer" ||
        decision === "steering"
    ) {
        return "switch";
    }

    if (
        decision === "stay" ||
        decision === "idle"
    ) {
        return "stay";
    }

    return decision || "unknown";
}

function getDecisionLabel(device) {
    const decision = normalizeDecision(device);

    if (decision === "switch") {
        if (device?.switched) {
            return "STEERED";
        }

        return "PROPOSAL";
    }

    if (decision === "stay") {
        return "STAY";
    }

    return String(
        device?.decision || "UNKNOWN",
    ).toUpperCase();
}

function getDecisionColor(device) {
    const decision = normalizeDecision(device);

    if (decision === "switch") {
        return device?.switched
            ? "success"
            : "warning";
    }

    if (decision === "stay") {
        return "default";
    }

    return "error";
}

function getScore(device, band) {
    const value =
        device?.scores?.[band];

    if (
        value === null ||
        value === undefined
    ) {
        return null;
    }

    const numeric = Number(value);

    return Number.isFinite(numeric)
        ? numeric
        : null;
}

function getCurrentScore(device) {
    return getScore(
        device,
        device?.current_band,
    );
}

function getBestScore(device) {
    return getScore(
        device,
        device?.best_band,
    );
}

function getMetric(device, band) {
    return (
        device?.metrics?.[band] || {}
    );
}

function getEngineRunning(data) {
    if (
        typeof data?.engine?.running ===
        "boolean"
    ) {
        return data.engine.running;
    }

    return false;
}

function getEngineMode(data) {
    const mode =
        data?.engine?.mode ||
        data?.mode;

    if (mode) {
        return String(mode).toLowerCase();
    }

    return "unknown";
}

function getCycle(data) {
    return (
        data?.engine?.cycle ??
        data?.cycle ??
        null
    );
}

function getInterval(data) {
    return (
        data?.engine?.interval ??
        data?.interval ??
        null
    );
}

function getLastCycle(data) {
    return (
        data?.engine?.last_cycle ??
        data?.timestamp ??
        null
    );
}

function getActions(data) {
    if (
        Array.isArray(data?.actions)
    ) {
        return data.actions;
    }

    if (
        Array.isArray(
            data?.recent_actions,
        )
    ) {
        return data.recent_actions;
    }

    if (
        Array.isArray(
            data?.history,
        )
    ) {
        return data.history;
    }

    return [];
}

// ============================================================================
// SMALL COMPONENTS
// ============================================================================

function StatusChip({ running }) {
    return (
        <Chip
            icon={
                running ? (
                    <CheckCircle />
                ) : (
                    <ErrorOutline />
                )
            }
            label={
                running
                    ? "ENGINE RUNNING"
                    : "ENGINE STOPPED"
            }
            color={
                running
                    ? "success"
                    : "error"
            }
            variant="filled"
            sx={{
                fontWeight: 700,
            }}
        />
    );
}

function MetricCard({
    title,
    value,
    subtitle,
    icon,
    color = "primary",
}) {
    return (
        <Card
            sx={{
                height: "100%",
            }}
        >
            <CardContent>
                <Stack
                    direction="row"
                    justifyContent="space-between"
                    alignItems="flex-start"
                    spacing={2}
                >
                    <Box>
                        <Typography
                            variant="body2"
                            color="text.secondary"
                        >
                            {title}
                        </Typography>

                        <Typography
                            variant="h5"
                            fontWeight={700}
                            sx={{
                                mt: 0.5,
                            }}
                        >
                            {value}
                        </Typography>

                        {subtitle && (
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                {subtitle}
                            </Typography>
                        )}
                    </Box>

                    <Box
                        sx={{
                            color: `${color}.main`,
                            display: "flex",
                            alignItems: "center",
                        }}
                    >
                        {icon}
                    </Box>
                </Stack>
            </CardContent>
        </Card>
    );
}

function ScoreBar({
    score,
    label,
    selected = false,
}) {
    const numeric = Number(score);

    const safeScore =
        Number.isFinite(numeric)
            ? Math.max(
                  0,
                  Math.min(
                      100,
                      numeric,
                  ),
              )
            : 0;

    return (
        <Box
            sx={{
                mb: 1.5,
            }}
        >
            <Stack
                direction="row"
                justifyContent="space-between"
                sx={{
                    mb: 0.5,
                }}
            >
                <Typography
                    variant="body2"
                    fontWeight={
                        selected
                            ? 700
                            : 500
                    }
                >
                    {label}
                </Typography>

                <Typography
                    variant="body2"
                    fontWeight={700}
                >
                    {formatScore(score)}
                </Typography>
            </Stack>

            <LinearProgress
                variant="determinate"
                value={safeScore}
                sx={{
                    height: 8,
                    borderRadius: 4,
                }}
            />
        </Box>
    );
}

// ============================================================================
// ENGINE STATUS
// ============================================================================

function EngineStatus({
    data,
    connected,
    actionLoading,
    onStart,
    onStop,
}) {
    const running =
        getEngineRunning(data);

    const mode =
        getEngineMode(data);

    const cycle =
        getCycle(data);

    const interval =
        getInterval(data);

    const lastCycle =
        getLastCycle(data);

    return (
        <Card>
            <CardContent>
                <Stack
                    direction={{
                        xs: "column",
                        md: "row",
                    }}
                    justifyContent="space-between"
                    alignItems={{
                        xs: "flex-start",
                        md: "center",
                    }}
                    spacing={2}
                >
                    <Stack spacing={1}>
                        <Typography
                            variant="h6"
                            fontWeight={700}
                        >
                            Steering Engine
                        </Typography>

                        <Stack
                            direction="row"
                            spacing={1}
                            flexWrap="wrap"
                        >
                            <StatusChip
                                running={running}
                            />

                            <Chip
                                label={
                                    mode ===
                                    "apply"
                                        ? "APPLY"
                                        : mode ===
                                          "dry_run"
                                        ? "DRY RUN"
                                        : mode.toUpperCase()
                                }
                                color={
                                    mode ===
                                    "apply"
                                        ? "success"
                                        : "warning"
                                }
                                variant="outlined"
                                sx={{
                                    fontWeight: 700,
                                }}
                            />

                            {connected && (
                                <Chip
                                    label="API CONNECTED"
                                    color="success"
                                    variant="outlined"
                                />
                            )}
                        </Stack>
                    </Stack>

                    <Stack
                        direction={{
                            xs: "column",
                            sm: "row",
                        }}
                        spacing={2}
                        alignItems={{
                            xs: "flex-start",
                            sm: "center",
                        }}
                    >
                        <Stack
                            direction="row"
                            spacing={4}
                            flexWrap="wrap"
                        >
                            <Box>
                                <Typography
                                    variant="caption"
                                    color="text.secondary"
                                >
                                    Cycle
                                </Typography>

                                <Typography
                                    variant="h6"
                                    fontWeight={700}
                                >
                                    {cycle ??
                                        "—"}
                                </Typography>
                            </Box>

                            <Box>
                                <Typography
                                    variant="caption"
                                    color="text.secondary"
                                >
                                    Interval
                                </Typography>

                                <Typography
                                    variant="h6"
                                    fontWeight={700}
                                >
                                    {interval !==
                                    null
                                        ? `${interval}s`
                                        : "—"}
                                </Typography>
                            </Box>

                            <Box>
                                <Typography
                                    variant="caption"
                                    color="text.secondary"
                                >
                                    Last cycle
                                </Typography>

                                <Typography
                                    variant="body1"
                                    fontWeight={600}
                                >
                                    {formatAge(
                                        lastCycle,
                                    )}
                                </Typography>

                                <Typography
                                    variant="caption"
                                    color="text.secondary"
                                >
                                    {formatTimestamp(
                                        lastCycle,
                                    )}
                                </Typography>
                            </Box>
                        </Stack>

                        <Divider
                            orientation="vertical"
                            flexItem
                            sx={{
                                display: {
                                    xs: "none",
                                    sm: "block",
                                },
                            }}
                        />

                        {!running ? (
                            <Button
                                variant="contained"
                                color="success"
                                startIcon={
                                    actionLoading ? (
                                        <CircularProgress
                                            size={18}
                                            color="inherit"
                                        />
                                    ) : (
                                        <PlayArrow />
                                    )
                                }
                                disabled={
                                    actionLoading ||
                                    !connected
                                }
                                onClick={
                                    onStart
                                }
                                sx={{
                                    minWidth: 160,
                                    fontWeight: 700,
                                }}
                            >
                                Start Steering
                            </Button>
                        ) : (
                            <Button
                                variant="contained"
                                color="error"
                                startIcon={
                                    actionLoading ? (
                                        <CircularProgress
                                            size={18}
                                            color="inherit"
                                        />
                                    ) : (
                                        <Stop />
                                    )
                                }
                                disabled={
                                    actionLoading
                                }
                                onClick={
                                    onStop
                                }
                                sx={{
                                    minWidth: 160,
                                    fontWeight: 700,
                                }}
                            >
                                Stop Steering
                            </Button>
                        )}
                    </Stack>
                </Stack>
            </CardContent>
        </Card>
    );
}

// ============================================================================
// LIVE ACTIONS
// ============================================================================

function ActiveSteering({ devices }) {
    const active = devices.filter(
        (device) =>
            normalizeDecision(
                device,
            ) === "switch",
    );

    if (active.length === 0) {
        return (
            <Alert
                severity="success"
                icon={<CheckCircle />}
            >
                <strong>
                    No steering in progress.
                </strong>{" "}
                The engine monitors stations
                and applies the configured
                threshold, preference, and
                cooldown rules.
            </Alert>
        );
    }

    return (
        <Stack spacing={1.5}>
            {active.map(
                (device, index) => {
                    const executed =
                        device.switched ===
                        true;

                    return (
                        <Alert
                            key={
                                device.mac ||
                                device.hostname ||
                                index
                            }
                            severity={
                                executed
                                    ? "success"
                                    : "warning"
                            }
                            icon={
                                executed ? (
                                    <CheckCircle />
                                ) : (
                                    <WarningAmber />
                                )
                            }
                        >
                            <Typography
                                fontWeight={700}
                            >
                                {executed
                                    ? "Steering executed"
                                    : "Steering decision"}
                            </Typography>

                            <Typography
                                variant="body2"
                            >
                                {device.mac ||
                                    device.hostname ||
                                    "Unknown station"}

                                {" : "}

                                {BAND_LABELS[
                                    device.current_band
                                ] ||
                                    device.current_band ||
                                    "?"}

                                {" → "}

                                {BAND_LABELS[
                                    device.target_band ||
                                        device.best_band
                                ] ||
                                    device.target_band ||
                                    device.best_band ||
                                    "?"}

                                {" — improvement "}
                                {formatNumber(
                                    device.improvement,
                                    1,
                                )}
                                {" points"}
                            </Typography>
                        </Alert>
                    );
                },
            )}
        </Stack>
    );
}

// ============================================================================
// DEVICES TABLE
// ============================================================================

function DevicesTable({
    devices,
    onSelect,
    selectedMac,
}) {
    return (
        <Card>
            <CardContent
                sx={{
                    pb: 1,
                }}
            >
                <Stack
                    direction="row"
                    justifyContent="space-between"
                    alignItems="center"
                >
                    <Box>
                        <Typography
                            variant="h6"
                            fontWeight={700}
                        >
                            Real-time Results
                        </Typography>

                        <Typography
                            variant="body2"
                            color="text.secondary"
                        >
                            Decisions calculated by
                            the backend.
                        </Typography>
                    </Box>

                    <Chip
                        icon={<Wifi />}
                        label={`${devices.length} station${
                            devices.length > 1
                                ? "s"
                                : ""
                        }`}
                        variant="outlined"
                    />
                </Stack>
            </CardContent>

            <TableContainer>
                <Table
                    size="small"
                    sx={{
                        minWidth: 900,
                    }}
                >
                    <TableHead>
                        <TableRow>
                            <TableCell>
                                Station
                            </TableCell>

                            <TableCell>
                                Type
                            </TableCell>

                            <TableCell>
                                Current
                            </TableCell>

                            <TableCell>
                                Best
                            </TableCell>

                            <TableCell align="right">
                                Current Score
                            </TableCell>

                            <TableCell align="right">
                                Best Score
                            </TableCell>

                            <TableCell align="right">
                                Improvement
                            </TableCell>

                            <TableCell>
                                Decision
                            </TableCell>
                        </TableRow>
                    </TableHead>

                    <TableBody>
                        {devices.length === 0 ? (
                            <TableRow>
                                <TableCell
                                    colSpan={8}
                                    align="center"
                                >
                                    <Typography
                                        color="text.secondary"
                                        sx={{
                                            py: 4,
                                        }}
                                    >
                                        No station
                                        available.
                                    </Typography>
                                </TableCell>
                            </TableRow>
                        ) : (
                            devices.map(
                                (
                                    device,
                                    index,
                                ) => {
                                    const currentScore =
                                        getCurrentScore(
                                            device,
                                        );

                                    const bestScore =
                                        getBestScore(
                                            device,
                                        );

                                    const isSelected =
                                        selectedMac ===
                                        device.mac;

                                    return (
                                        <TableRow
                                            key={
                                                device.mac ||
                                                device.hostname ||
                                                index
                                            }
                                            hover
                                            selected={
                                                isSelected
                                            }
                                            onClick={() =>
                                                onSelect(
                                                    device.mac,
                                                )
                                            }
                                            sx={{
                                                cursor: "pointer",
                                            }}
                                        >
                                            <TableCell>
                                                <Stack
                                                    spacing={
                                                        0.25
                                                    }
                                                >
                                                    <Typography
                                                        fontWeight={
                                                            700
                                                        }
                                                    >
                                                        {device.mac ||
                                                            "Unknown"}
                                                    </Typography>

                                                    {device.hostname &&
                                                        device.hostname !==
                                                            device.mac && (
                                                            <Typography
                                                                variant="caption"
                                                                color="text.secondary"
                                                            >
                                                                {
                                                                    device.hostname
                                                                }
                                                            </Typography>
                                                        )}
                                                </Stack>
                                            </TableCell>

                                            <TableCell>
                                                <Chip
                                                    size="small"
                                                    label={
                                                        device.device_type ||
                                                        "Unknown"
                                                    }
                                                    variant="outlined"
                                                />
                                            </TableCell>

                                            <TableCell>
                                                <Typography
                                                    fontWeight={
                                                        600
                                                    }
                                                >
                                                    {BAND_LABELS[
                                                        device.current_band
                                                    ] ||
                                                        device.current_band ||
                                                        "—"}
                                                </Typography>
                                            </TableCell>

                                            <TableCell>
                                                <Typography
                                                    fontWeight={
                                                        700
                                                    }
                                                >
                                                    {BAND_LABELS[
                                                        device.best_band
                                                    ] ||
                                                        device.best_band ||
                                                        "—"}
                                                </Typography>
                                            </TableCell>

                                            <TableCell align="right">
                                                {formatScore(
                                                    currentScore,
                                                )}
                                            </TableCell>

                                            <TableCell align="right">
                                                {formatScore(
                                                    bestScore,
                                                )}
                                            </TableCell>

                                            <TableCell align="right">
                                                <Typography
                                                    fontWeight={
                                                        700
                                                    }
                                                    color={
                                                        Number(
                                                            device.improvement ||
                                                                0,
                                                        ) >=
                                                        Number(
                                                            device.switch_threshold ||
                                                                0,
                                                        )
                                                            ? "success.main"
                                                            : "text.primary"
                                                    }
                                                >
                                                    {formatNumber(
                                                        device.improvement,
                                                        1,
                                                    )}
                                                </Typography>
                                            </TableCell>

                                            <TableCell>
                                                <Chip
                                                    size="small"
                                                    label={getDecisionLabel(
                                                        device,
                                                    )}
                                                    color={getDecisionColor(
                                                        device,
                                                    )}
                                                    variant={
                                                        normalizeDecision(
                                                            device,
                                                        ) ===
                                                        "stay"
                                                            ? "outlined"
                                                            : "filled"
                                                    }
                                                    sx={{
                                                        fontWeight: 700,
                                                    }}
                                                />
                                            </TableCell>
                                        </TableRow>
                                    );
                                },
                            )
                        )}
                    </TableBody>
                </Table>
            </TableContainer>
        </Card>
    );
}

// ============================================================================
// DEVICE DETAILS
// ============================================================================

function DeviceDetails({ device }) {
    if (!device) {
        return (
            <Card>
                <CardContent>
                    <Stack
                        alignItems="center"
                        spacing={1}
                        sx={{
                            py: 5,
                        }}
                    >
                        <Radio
                            sx={{
                                fontSize: 42,
                            }}
                        />

                        <Typography
                            variant="h6"
                        >
                            Select a station
                        </Typography>

                        <Typography
                            variant="body2"
                            color="text.secondary"
                            align="center"
                        >
                            Full engine diagnostics
                            will appear here.
                        </Typography>
                    </Stack>
                </CardContent>
            </Card>
        );
    }

    const currentScore =
        getCurrentScore(device);

    const bestScore =
        getBestScore(device);

    const requirements =
        device.requirements || {};

    const thresholds =
        requirements.thresholds || {};

    const weights =
        device.weights || {};

    return (
        <Stack spacing={2}>
            <Card>
                <CardContent>
                    <Stack
                        direction={{
                            xs: "column",
                            md: "row",
                        }}
                        justifyContent="space-between"
                        spacing={2}
                    >
                        <Box>
                            <Typography
                                variant="h6"
                                fontWeight={700}
                            >
                                Station Diagnostics
                            </Typography>

                            <Typography
                                variant="body1"
                                sx={{
                                    fontFamily:
                                        "monospace",
                                    mt: 0.5,
                                }}
                            >
                                {device.mac ||
                                    device.hostname ||
                                    "Unknown"}
                            </Typography>
                        </Box>

                        <Stack
                            direction="row"
                            spacing={1}
                            flexWrap="wrap"
                        >
                            <Chip
                                label={
                                    device.priority ||
                                    "medium"
                                }
                                variant="outlined"
                            />

                            <Chip
                                label={
                                    device.device_type ||
                                    "Unknown"
                                }
                                variant="outlined"
                            />

                            <Chip
                                label={getDecisionLabel(
                                    device,
                                )}
                                color={getDecisionColor(
                                    device,
                                )}
                                sx={{
                                    fontWeight: 700,
                                }}
                            />
                        </Stack>
                    </Stack>
                </CardContent>
            </Card>

            <Card>
                <CardContent>
                    <Typography
                        variant="h6"
                        fontWeight={700}
                        sx={{
                            mb: 2,
                        }}
                    >
                        Engine Decision
                    </Typography>

                    <Grid
                        container
                        spacing={2}
                    >
                        <Grid
                            item
                            xs={12}
                            md={3}
                        >
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                Current Band
                            </Typography>

                            <Typography
                                variant="h6"
                                fontWeight={700}
                            >
                                {BAND_LABELS[
                                    device.current_band
                                ] ||
                                    device.current_band ||
                                    "—"}
                            </Typography>
                        </Grid>

                        <Grid
                            item
                            xs={12}
                            md={3}
                        >
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                Best Band
                            </Typography>

                            <Typography
                                variant="h6"
                                fontWeight={700}
                            >
                                {BAND_LABELS[
                                    device.best_band
                                ] ||
                                    device.best_band ||
                                    "—"}
                            </Typography>
                        </Grid>

                        <Grid
                            item
                            xs={12}
                            md={2}
                        >
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                Current Score
                            </Typography>

                            <Typography
                                variant="h6"
                                fontWeight={700}
                            >
                                {formatScore(
                                    currentScore,
                                )}
                            </Typography>
                        </Grid>

                        <Grid
                            item
                            xs={12}
                            md={2}
                        >
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                Best Score
                            </Typography>

                            <Typography
                                variant="h6"
                                fontWeight={700}
                            >
                                {formatScore(
                                    bestScore,
                                )}
                            </Typography>
                        </Grid>

                        <Grid
                            item
                            xs={12}
                            md={2}
                        >
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                Improvement
                            </Typography>

                            <Typography
                                variant="h6"
                                fontWeight={700}
                                color={
                                    Number(
                                        device.improvement ||
                                            0,
                                    ) > 0
                                        ? "success.main"
                                        : "text.primary"
                                }
                            >
                                {formatNumber(
                                    device.improvement,
                                    1,
                                )}
                            </Typography>
                        </Grid>
                    </Grid>

                    <Divider
                        sx={{
                            my: 2,
                        }}
                    />

                    <Stack spacing={1}>
                        <Typography
                            variant="body2"
                            fontWeight={700}
                        >
                            Reason
                        </Typography>

                        <Typography
                            variant="body2"
                            color="text.secondary"
                        >
                            {device?.reasons
                                ?.decision ||
                                device?.reason ||
                                "No reason provided."}
                        </Typography>
                    </Stack>

                    <Stack
                        direction="row"
                        spacing={1}
                        flexWrap="wrap"
                        sx={{
                            mt: 2,
                        }}
                    >
                        <Chip
                            size="small"
                            label={`Threshold: ${formatNumber(
                                device.switch_threshold,
                                1,
                            )}`}
                            variant="outlined"
                        />

                        <Chip
                            size="small"
                            label={`Cooldown: ${formatNumber(
                                device.cooldown,
                                1,
                            )} s`}
                            variant="outlined"
                        />

                        <Chip
                            size="small"
                            label={`Remaining: ${formatNumber(
                                device.cooldown_remaining,
                                1,
                            )} s`}
                            variant="outlined"
                        />

                        <Chip
                            size="small"
                            label={
                                device.switched
                                    ? "Action executed"
                                    : "No action executed"
                            }
                            color={
                                device.switched
                                    ? "success"
                                    : "default"
                            }
                            variant="outlined"
                        />
                    </Stack>
                </CardContent>
            </Card>

            <Card>
                <CardContent>
                    <Typography
                        variant="h6"
                        fontWeight={700}
                        sx={{
                            mb: 2,
                        }}
                    >
                        Multi-Metric Scores
                    </Typography>

                    {BANDS.map(
                        (band) => (
                            <ScoreBar
                                key={
                                    band.key
                                }
                                label={
                                    band.label
                                }
                                score={getScore(
                                    device,
                                    band.key,
                                )}
                                selected={
                                    device.best_band ===
                                    band.key
                                }
                            />
                        ),
                    )}
                </CardContent>
            </Card>

            <Card>
                <CardContent>
                    <Typography
                        variant="h6"
                        fontWeight={700}
                        sx={{
                            mb: 2,
                        }}
                    >
                        Metrics per Band
                    </Typography>

                    <TableContainer
                        component={Paper}
                        variant="outlined"
                    >
                        <Table size="small">
                            <TableHead>
                                <TableRow>
                                    <TableCell>
                                        Metric
                                    </TableCell>

                                    {BANDS.map(
                                        (
                                            band,
                                        ) => (
                                            <TableCell
                                                key={
                                                    band.key
                                                }
                                                align="right"
                                            >
                                                {
                                                    band.label
                                                }
                                            </TableCell>
                                        ),
                                    )}
                                </TableRow>
                            </TableHead>

                            <TableBody>
                                <TableRow>
                                    <TableCell>
                                        Clients
                                    </TableCell>

                                    {BANDS.map(
                                        (
                                            band,
                                        ) => {
                                            const metric =
                                                getMetric(
                                                    device,
                                                    band.key,
                                                );

                                            return (
                                                <TableCell
                                                    key={
                                                        band.key
                                                    }
                                                    align="right"
                                                >
                                                    {metric.clients ??
                                                        0}
                                                </TableCell>
                                            );
                                        },
                                    )}
                                </TableRow>

                                <TableRow>
                                    <TableCell>
                                        RSSI
                                    </TableCell>

                                    {BANDS.map(
                                        (
                                            band,
                                        ) => {
                                            const metric =
                                                getMetric(
                                                    device,
                                                    band.key,
                                                );

                                            return (
                                                <TableCell
                                                    key={
                                                        band.key
                                                    }
                                                    align="right"
                                                >
                                                    {metric.rssi_known
                                                        ? `${formatNumber(
                                                              metric.rssi,
                                                              1,
                                                          )} dBm`
                                                        : "Unknown"}
                                                </TableCell>
                                            );
                                        },
                                    )}
                                </TableRow>

                                <TableRow>
                                    <TableCell>
                                        Throughput
                                    </TableCell>

                                    {BANDS.map(
                                        (
                                            band,
                                        ) => {
                                            const metric =
                                                getMetric(
                                                    device,
                                                    band.key,
                                                );

                                            return (
                                                <TableCell
                                                    key={
                                                        band.key
                                                    }
                                                    align="right"
                                                >
                                                    {metric.throughput_known
                                                        ? formatMbps(
                                                              metric.throughput_mbps,
                                                          )
                                                        : "Unknown"}
                                                </TableCell>
                                            );
                                        },
                                    )}
                                </TableRow>

                                <TableRow>
                                    <TableCell>
                                        Airtime
                                    </TableCell>

                                    {BANDS.map(
                                        (
                                            band,
                                        ) => {
                                            const metric =
                                                getMetric(
                                                    device,
                                                    band.key,
                                                );

                                            return (
                                                <TableCell
                                                    key={
                                                        band.key
                                                    }
                                                    align="right"
                                                >
                                                    {metric.airtime_known
                                                        ? formatPercent(
                                                              metric.airtime,
                                                          )
                                                        : "Unknown"}
                                                </TableCell>
                                            );
                                        },
                                    )}
                                </TableRow>

                                <TableRow>
                                    <TableCell>
                                        TX Power
                                    </TableCell>

                                    {BANDS.map(
                                        (
                                            band,
                                        ) => {
                                            const metric =
                                                getMetric(
                                                    device,
                                                    band.key,
                                                );

                                            return (
                                                <TableCell
                                                    key={
                                                        band.key
                                                    }
                                                    align="right"
                                                >
                                                    {metric.txpower !==
                                                        null &&
                                                    metric.txpower !==
                                                        undefined
                                                        ? `${formatNumber(
                                                              metric.txpower,
                                                              1,
                                                          )} dBm`
                                                        : "Unknown"}
                                                </TableCell>
                                            );
                                        },
                                    )}
                                </TableRow>

                                <TableRow>
                                    <TableCell>
                                        Associated
                                    </TableCell>

                                    {BANDS.map(
                                        (
                                            band,
                                        ) => {
                                            const metric =
                                                getMetric(
                                                    device,
                                                    band.key,
                                                );

                                            return (
                                                <TableCell
                                                    key={
                                                        band.key
                                                    }
                                                    align="right"
                                                >
                                                    <Chip
                                                        size="small"
                                                        label={
                                                            metric.associated
                                                                ? "YES"
                                                                : "NO"
                                                        }
                                                        color={
                                                            metric.associated
                                                                ? "success"
                                                                : "default"
                                                        }
                                                        variant="outlined"
                                                    />
                                                </TableCell>
                                            );
                                        },
                                    )}
                                </TableRow>
                            </TableBody>
                        </Table>
                    </TableContainer>
                </CardContent>
            </Card>

            <Grid
                container
                spacing={2}
            >
                <Grid
                    item
                    xs={12}
                    md={6}
                >
                    <Card
                        sx={{
                            height: "100%",
                        }}
                    >
                        <CardContent>
                            <Typography
                                variant="h6"
                                fontWeight={700}
                                sx={{
                                    mb: 2,
                                }}
                            >
                                Client Requirements
                            </Typography>

                            <Stack spacing={1.5}>
                                <Stack
                                    direction="row"
                                    justifyContent="space-between"
                                >
                                    <Typography>
                                        Preferred Band
                                    </Typography>

                                    <Chip
                                        label={
                                            BAND_LABELS[
                                                device.preferred_band
                                            ] ||
                                            device.preferred_band ||
                                            "—"
                                        }
                                        size="small"
                                    />
                                </Stack>

                                <Stack
                                    direction="row"
                                    justifyContent="space-between"
                                >
                                    <Typography>
                                        Minimum Throughput
                                    </Typography>

                                    <Typography fontWeight={700}>
                                        {formatMbps(
                                            requirements.min_throughput_mbps,
                                        )}
                                    </Typography>
                                </Stack>

                                <Stack
                                    direction="row"
                                    justifyContent="space-between"
                                >
                                    <Typography>
                                        Maximum Airtime
                                    </Typography>

                                    <Typography fontWeight={700}>
                                        {formatPercent(
                                            requirements.max_airtime_percent,
                                        )}
                                    </Typography>
                                </Stack>

                                <Divider />

                                <Typography
                                    variant="subtitle2"
                                    fontWeight={700}
                                >
                                    Enabled Bands
                                </Typography>

                                <Stack
                                    direction="row"
                                    spacing={1}
                                    flexWrap="wrap"
                                >
                                    {BANDS.map(
                                        (
                                            band,
                                        ) => (
                                            <Chip
                                                key={
                                                    band.key
                                                }
                                                label={
                                                    band.label
                                                }
                                                color={
                                                    requirements
                                                        ?.bands?.[
                                                        band.key
                                                    ]
                                                        ? "success"
                                                        : "default"
                                                }
                                                variant={
                                                    requirements
                                                        ?.bands?.[
                                                        band.key
                                                    ]
                                                        ? "filled"
                                                        : "outlined"
                                                }
                                                size="small"
                                            />
                                        ),
                                    )}
                                </Stack>
                            </Stack>
                        </CardContent>
                    </Card>
                </Grid>

                <Grid
                    item
                    xs={12}
                    md={6}
                >
                    <Card
                        sx={{
                            height: "100%",
                        }}
                    >
                        <CardContent>
                            <Typography
                                variant="h6"
                                fontWeight={700}
                                sx={{
                                    mb: 2,
                                }}
                            >
                                Minimum RSSI
                            </Typography>

                            <Stack spacing={1.5}>
                                {BANDS.map(
                                    (
                                        band,
                                    ) => (
                                        <Stack
                                            key={
                                                band.key
                                            }
                                            direction="row"
                                            justifyContent="space-between"
                                        >
                                            <Typography>
                                                {
                                                    band.label
                                                }
                                            </Typography>

                                            <Typography
                                                fontWeight={
                                                    700
                                                }
                                            >
                                                {thresholds?.[
                                                    band.key
                                                ]?.min_rssi !==
                                                undefined
                                                    ? `${formatNumber(
                                                          thresholds[
                                                              band.key
                                                          ]
                                                              .min_rssi,
                                                          1,
                                                      )} dBm`
                                                    : "—"}
                                            </Typography>
                                        </Stack>
                                    ),
                                )}
                            </Stack>
                        </CardContent>
                    </Card>
                </Grid>
            </Grid>

            <Card>
                <CardContent>
                    <Stack
                        direction="row"
                        spacing={1}
                        alignItems="center"
                        sx={{
                            mb: 2,
                        }}
                    >
                        <Memory />

                        <Typography
                            variant="h6"
                            fontWeight={700}
                        >
                            Automatic Weights
                        </Typography>

                        <Chip
                            size="small"
                            label="BACKEND"
                            color="primary"
                            variant="outlined"
                        />
                    </Stack>

                    <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{
                            mb: 2,
                        }}
                    >
                        These weights are calculated by
                        the backend engine from the
                        client's requirements. They are
                        displayed as read-only values.
                    </Typography>

                    <Grid
                        container
                        spacing={2}
                    >
                        {[
                            [
                                "clients",
                                "Clients",
                            ],
                            [
                                "rssi",
                                "RSSI",
                            ],
                            [
                                "airtime",
                                "Airtime",
                            ],
                            [
                                "throughput",
                                "Throughput",
                            ],
                            [
                                "txpower",
                                "TX Power",
                            ],
                        ].map(
                            ([
                                key,
                                label,
                            ]) => {
                                const value =
                                    Number(
                                        weights[
                                            key
                                        ],
                                    );

                                return (
                                    <Grid
                                        item
                                        xs={6}
                                        md={2.4}
                                        key={key}
                                    >
                                        <Paper
                                            variant="outlined"
                                            sx={{
                                                p: 2,
                                                textAlign:
                                                    "center",
                                            }}
                                        >
                                            <Typography
                                                variant="caption"
                                                color="text.secondary"
                                            >
                                                {
                                                    label
                                                }
                                            </Typography>

                                            <Typography
                                                variant="h6"
                                                fontWeight={
                                                    700
                                                }
                                            >
                                                {Number.isFinite(
                                                    value,
                                                )
                                                    ? `${(
                                                          value *
                                                          100
                                                      ).toFixed(
                                                          1,
                                                      )}%`
                                                    : "—"}
                                            </Typography>
                                        </Paper>
                                    </Grid>
                                );
                            },
                        )}
                    </Grid>
                </CardContent>
            </Card>

            {Object.keys(
                device?.reasons
                    ?.rejection_reasons ||
                    {},
            ).length > 0 && (
                <Card>
                    <CardContent>
                        <Stack
                            direction="row"
                            spacing={1}
                            alignItems="center"
                            sx={{
                                mb: 2,
                            }}
                        >
                            <WarningAmber color="warning" />

                            <Typography
                                variant="h6"
                                fontWeight={700}
                            >
                                Rejected Bands
                            </Typography>
                        </Stack>

                        <Stack spacing={1}>
                            {Object.entries(
                                device.reasons
                                    .rejection_reasons,
                            ).map(
                                ([
                                    band,
                                    reason,
                                ]) => (
                                    <Alert
                                        key={
                                            band
                                        }
                                        severity="warning"
                                    >
                                        <strong>
                                            {BAND_LABELS[
                                                band
                                            ] ||
                                                band}
                                        </strong>
                                        {": "}
                                        {reason}
                                    </Alert>
                                ),
                            )}
                        </Stack>
                    </CardContent>
                </Card>
            )}
        </Stack>
    );
}

// ============================================================================
// ACTION HISTORY
// ============================================================================

function ActionHistory({ actions }) {
    if (!actions.length) {
        return null;
    }

    return (
        <Card>
            <CardContent>
                <Typography
                    variant="h6"
                    fontWeight={700}
                    sx={{
                        mb: 2,
                    }}
                >
                    Recent Actions
                </Typography>

                <TableContainer>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>
                                    Date
                                </TableCell>

                                <TableCell>
                                    Station
                                </TableCell>

                                <TableCell>
                                    Source
                                </TableCell>

                                <TableCell>
                                    Target
                                </TableCell>

                                <TableCell>
                                    Improvement
                                </TableCell>

                                <TableCell>
                                    Status
                                </TableCell>
                            </TableRow>
                        </TableHead>

                        <TableBody>
                            {actions
                                .slice(0, 10)
                                .map(
                                    (
                                        action,
                                        index,
                                    ) => (
                                        <TableRow
                                            key={
                                                action.id ||
                                                index
                                            }
                                        >
                                            <TableCell>
                                                {formatTimestamp(
                                                    action.timestamp,
                                                )}
                                            </TableCell>

                                            <TableCell
                                                sx={{
                                                    fontFamily:
                                                        "monospace",
                                                }}
                                            >
                                                {action.station ||
                                                    action.mac ||
                                                    "—"}
                                            </TableCell>

                                            <TableCell>
                                                {BAND_LABELS[
                                                    action.source_band
                                                ] ||
                                                    action.source_band ||
                                                    "—"}
                                            </TableCell>

                                            <TableCell>
                                                {BAND_LABELS[
                                                    action.target_band
                                                ] ||
                                                    action.target_band ||
                                                    "—"}
                                            </TableCell>

                                            <TableCell>
                                                {formatNumber(
                                                    action.improvement,
                                                    1,
                                                )}
                                            </TableCell>

                                            <TableCell>
                                                <Chip
                                                    size="small"
                                                    label={
                                                        action.status ||
                                                        action.action_type ||
                                                        "unknown"
                                                    }
                                                    color={
                                                        action.status ===
                                                        "steering_success"
                                                            ? "success"
                                                            : action.status ===
                                                              "error"
                                                            ? "error"
                                                            : "default"
                                                    }
                                                    variant="outlined"
                                                />
                                            </TableCell>
                                        </TableRow>
                                    ),
                                )}
                        </TableBody>
                    </Table>
                </TableContainer>
            </CardContent>
        </Card>
    );
}

// ============================================================================
// MAIN PAGE
// ============================================================================

export default function Steering() {
    const [data, setData] =
        useState(null);

    const [loading, setLoading] =
        useState(true);

    const [error, setError] =
        useState("");

    const [connected, setConnected] =
        useState(false);

    const [lastPoll, setLastPoll] =
        useState(null);

    const [selectedMac, setSelectedMac] =
        useState(null);

    const [
        engineActionLoading,
        setEngineActionLoading,
    ] = useState(false);

    // ------------------------------------------------------------------------
    // LOAD
    // ------------------------------------------------------------------------

    const loadSteering = useCallback(
        async () => {
            try {
                const response =
                    await fetch(
                        `${API_URL}/api/steering`,
                        {
                            method: "GET",
                            cache: "no-store",
                            headers: {
                                Accept:
                                    "application/json",
                            },
                        },
                    );

                if (!response.ok) {
                    throw new Error(
                        `HTTP ${response.status}`,
                    );
                }

                const payload =
                    await response.json();

                setData(payload);
                setConnected(true);
                setError("");
                setLastPoll(
                    Date.now(),
                );
            } catch (err) {
                console.error(
                    "Unable to load steering state:",
                    err,
                );

                setConnected(false);

                setError(
                    err?.message ||
                        "Unable to retrieve the steering state.",
                );
            } finally {
                setLoading(false);
            }
        },
        [],
    );

    // ------------------------------------------------------------------------
    // START / STOP ENGINE
    // ------------------------------------------------------------------------

    const controlSteering =
        useCallback(
            async (action) => {
                if (
                    action !== "start" &&
                    action !== "stop"
                ) {
                    return;
                }

                setEngineActionLoading(
                    true,
                );

                try {
                    const response =
                        await fetch(
                            `${API_URL}/api/steering/${action}`,
                            {
                                method: "POST",
                                headers: {
                                    Accept:
                                        "application/json",
                                    "Content-Type":
                                        "application/json",
                                },
                            },
                        );

                    const payload =
                        await response
                            .json()
                            .catch(
                                () => ({}),
                            );

                    if (!response.ok) {
                        throw new Error(
                            payload.message ||
                                `HTTP ${response.status}`,
                        );
                    }

                    setError("");

                    await loadSteering();
                } catch (err) {
                    console.error(
                        `Unable to ${action} steering:`,
                        err,
                    );

                    setError(
                        err?.message ||
                            `Unable to ${action} steering.`,
                    );
                } finally {
                    setEngineActionLoading(
                        false,
                    );
                }
            },
            [loadSteering],
        );

    const startSteering =
        useCallback(() => {
            controlSteering("start");
        }, [controlSteering]);

    const stopSteering =
        useCallback(() => {
            controlSteering("stop");
        }, [controlSteering]);

    // ------------------------------------------------------------------------
    // REAL-TIME POLLING
    // ------------------------------------------------------------------------

    useEffect(() => {
        loadSteering();

        const timer =
            setInterval(
                loadSteering,
                POLL_INTERVAL,
            );

        return () => {
            clearInterval(timer);
        };
    }, [
        loadSteering,
    ]);

    // ------------------------------------------------------------------------
    // DEVICES
    // ------------------------------------------------------------------------

    const devices = useMemo(
        () =>
            Array.isArray(
                data?.devices,
            )
                ? data.devices
                : [],
        [data],
    );

    // ------------------------------------------------------------------------
    // SELECTED DEVICE
    // ------------------------------------------------------------------------

    const selectedDevice =
        useMemo(() => {
            if (!devices.length) {
                return null;
            }

            if (selectedMac) {
                const found =
                    devices.find(
                        (device) =>
                            device.mac ===
                            selectedMac,
                    );

                if (found) {
                    return found;
                }
            }

            return devices[0];
        }, [
            devices,
            selectedMac,
        ]);

    // ------------------------------------------------------------------------
    // GLOBAL STATS
    // ------------------------------------------------------------------------

    const switchProposals =
        useMemo(
            () =>
                devices.filter(
                    (device) =>
                        normalizeDecision(
                            device,
                        ) === "switch",
                ).length,
            [devices],
        );

    const executedSwitches =
        useMemo(
            () =>
                devices.filter(
                    (device) =>
                        device.switched ===
                        true,
                ).length,
            [devices],
        );

    const stayingDevices =
        useMemo(
            () =>
                devices.filter(
                    (device) =>
                        normalizeDecision(
                            device,
                        ) === "stay",
                ).length,
            [devices],
        );

    const engineRunning =
        getEngineRunning(data);

    const lastCycle =
        getLastCycle(data);

    const actions =
        getActions(data);

    // ------------------------------------------------------------------------
    // LOADING
    // ------------------------------------------------------------------------

    if (
        loading &&
        !data
    ) {
        return (
            <>
                <Header />

                <Box
                    sx={{
                        p: 3,
                    }}
                >
                    <Stack
                        alignItems="center"
                        justifyContent="center"
                        spacing={2}
                        sx={{
                            minHeight: 400,
                        }}
                    >
                        <CircularProgress />

                        <Typography color="text.secondary">
                            Connecting to the
                            steering engine...
                        </Typography>
                    </Stack>
                </Box>
            </>
        );
    }

    // ------------------------------------------------------------------------
    // RENDER
    // ------------------------------------------------------------------------

    return (
        <>
            <Header />

            <Box
                sx={{
                    p: {
                        xs: 2,
                        md: 3,
                    },
                }}
            >
                {/* ========================================================= */}
                {/* HEADER */}
                {/* ========================================================= */}

                <Stack
                    direction={{
                        xs: "column",
                        md: "row",
                    }}
                    justifyContent="space-between"
                    alignItems={{
                        xs: "flex-start",
                        md: "center",
                    }}
                    spacing={2}
                    sx={{
                        mb: 3,
                    }}
                >
                    <Box>
                        <Typography
                            variant="h4"
                            fontWeight={800}
                        >
                            Steering
                        </Typography>

                        <Typography
                            variant="body1"
                            color="text.secondary"
                        >
                            Real-time monitoring of the
                            multi-band placement engine.
                        </Typography>
                    </Box>

                    <Stack
                        direction="row"
                        spacing={1}
                        alignItems="center"
                    >
                        <Chip
                            icon={<Refresh />}
                            label={
                                connected
                                    ? "LIVE · 1 s"
                                    : "OFFLINE"
                            }
                            color={
                                connected
                                    ? "success"
                                    : "error"
                            }
                            variant={
                                connected
                                    ? "filled"
                                    : "outlined"
                            }
                            sx={{
                                fontWeight: 700,
                            }}
                        />

                        {lastPoll && (
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                API{" "}
                                {formatAge(
                                    lastPoll /
                                        1000,
                                )}
                            </Typography>
                        )}
                    </Stack>
                </Stack>

                {/* ========================================================= */}
                {/* ERROR */}
                {/* ========================================================= */}

                {error && (
                    <Alert
                        severity={
                            data
                                ? "warning"
                                : "error"
                        }
                        sx={{
                            mb: 2,
                        }}
                    >
                        <strong>
                            Steering API:
                        </strong>{" "}
                        {error}
                        {data &&
                            " — displaying the last known state."}
                    </Alert>
                )}

                {/* ========================================================= */}
                {/* ENGINE */}
                {/* ========================================================= */}

                <Box
                    sx={{
                        mb: 2,
                    }}
                >
                    <EngineStatus
                        data={data}
                        connected={
                            connected
                        }
                        actionLoading={
                            engineActionLoading
                        }
                        onStart={
                            startSteering
                        }
                        onStop={
                            stopSteering
                        }
                    />
                </Box>

                {/* ========================================================= */}
                {/* ENGINE TIMELINE */}
                {/* ========================================================= */}

                <Card
                    sx={{
                        mb: 2,
                    }}
                >
                    <CardContent>
                        <Stack
                            direction={{
                                xs: "column",
                                md: "row",
                            }}
                            spacing={2}
                            alignItems={{
                                xs: "flex-start",
                                md: "center",
                            }}
                        >
                            <Timeline
                                color={
                                    engineRunning
                                        ? "success"
                                        : "disabled"
                                }
                            />

                            <Box
                                sx={{
                                    flex: 1,
                                }}
                            >
                                <Typography
                                    fontWeight={700}
                                >
                                    Control Loop
                                </Typography>

                                <Typography
                                    variant="body2"
                                    color="text.secondary"
                                >
                                    Collection → metrics
                                    → scores → constraints
                                    → threshold → cooldown
                                    → steering.
                                </Typography>
                            </Box>

                            <Typography
                                variant="body2"
                                fontWeight={600}
                            >
                                Last cycle:{" "}
                                {formatAge(
                                    lastCycle,
                                )}
                            </Typography>
                        </Stack>
                    </CardContent>
                </Card>

                {/* ========================================================= */}
                {/* GLOBAL STATS */}
                {/* ========================================================= */}

                <Grid
                    container
                    spacing={2}
                    sx={{
                        mb: 2,
                    }}
                >
                    <Grid
                        item
                        xs={12}
                        sm={6}
                        md={3}
                    >
                        <MetricCard
                            title="Stations"
                            value={
                                devices.length
                            }
                            subtitle="Supervised stations"
                            icon={
                                <Wifi fontSize="large" />
                            }
                        />
                    </Grid>

                    <Grid
                        item
                        xs={12}
                        sm={6}
                        md={3}
                    >
                        <MetricCard
                            title="STAY"
                            value={
                                stayingDevices
                            }
                            subtitle="No steering required"
                            icon={
                                <CheckCircle fontSize="large" />
                            }
                            color="success"
                        />
                    </Grid>

                    <Grid
                        item
                        xs={12}
                        sm={6}
                        md={3}
                    >
                        <MetricCard
                            title="Steering"
                            value={
                                switchProposals
                            }
                            subtitle="Decisions / proposals"
                            icon={
                                <TrendingUp fontSize="large" />
                            }
                            color="warning"
                        />
                    </Grid>

                    <Grid
                        item
                        xs={12}
                        sm={6}
                        md={3}
                    >
                        <MetricCard
                            title="Executed"
                            value={
                                executedSwitches
                            }
                            subtitle="Steering actions applied"
                            icon={
                                <Speed fontSize="large" />
                            }
                            color="success"
                        />
                    </Grid>
                </Grid>

                {/* ========================================================= */}
                {/* ACTIVE STEERING */}
                {/* ========================================================= */}

                <Box
                    sx={{
                        mb: 2,
                    }}
                >
                    <ActiveSteering
                        devices={
                            devices
                        }
                    />
                </Box>

                {/* ========================================================= */}
                {/* DEVICE TABLE */}
                {/* ========================================================= */}

                <Box
                    sx={{
                        mb: 2,
                    }}
                >
                    <DevicesTable
                        devices={
                            devices
                        }
                        selectedMac={
                            selectedMac
                        }
                        onSelect={
                            setSelectedMac
                        }
                    />
                </Box>

                {/* ========================================================= */}
                {/* DETAILS */}
                {/* ========================================================= */}

                <Box
                    sx={{
                        mb: 2,
                    }}
                >
                    <DeviceDetails
                        device={
                            selectedDevice
                        }
                    />
                </Box>

                {/* ========================================================= */}
                {/* HISTORY */}
                {/* ========================================================= */}

                <ActionHistory
                    actions={
                        actions
                    }
                />

                {/* ========================================================= */}
                {/* FOOTER STATUS */}
                {/* ========================================================= */}

                <Stack
                    direction={{
                        xs: "column",
                        md: "row",
                    }}
                    justifyContent="space-between"
                    spacing={1}
                    sx={{
                        mt: 2,
                    }}
                >
                    <Typography
                        variant="caption"
                        color="text.secondary"
                    >
                        Backend state:{" "}
                        {data?.status ||
                            "unknown"}
                    </Typography>

                    <Typography
                        variant="caption"
                        color="text.secondary"
                    >
                        State timestamp:{" "}
                        {formatTimestamp(
                            data?.timestamp,
                        )}
                    </Typography>

                    <Typography
                        variant="caption"
                        color="text.secondary"
                    >
                        Frontend polling:{" "}
                        {POLL_INTERVAL /
                            1000}
                        s
                    </Typography>
                </Stack>
            </Box>
        </>
    );
}
