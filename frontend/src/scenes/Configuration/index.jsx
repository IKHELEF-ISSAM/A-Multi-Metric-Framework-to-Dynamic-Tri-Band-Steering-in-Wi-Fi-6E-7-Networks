import { API_BASE_URL } from "../../api";
import {
    Alert,
    Box,
    Button,
    Checkbox,
    CircularProgress,
    Divider,
    FormControl,
    FormControlLabel,
    Grid,
    InputLabel,
    MenuItem,
    Paper,
    Select,
    Snackbar,
    TextField,
    Typography,
} from "@mui/material";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import SaveOutlinedIcon from "@mui/icons-material/SaveOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import { useEffect, useMemo, useState } from "react";
import Header from "../../components/Header";

const API_URL = API_BASE_URL;

const DEFAULT_RULE = {
    device_type: "Unknown",
    priority: "medium",

    bands: {
        "2G": true,
        "5G": true,
        "6G": true,
    },

    preferred_band: "5G",

    /*
     * IMPORTANT:
     * weights are now DERIVED automatically.
     * They are not user-configurable.
     */
    weights: {
        clients: 0.10,
        rssi: 0.30,
        airtime: 0.25,
        throughput: 0.25,
        txpower: 0.10,
    },

    thresholds: {
        "2G": { min_rssi: -75 },
        "5G": { min_rssi: -70 },
        "6G": { min_rssi: -65 },
    },

    min_throughput_mbps: 5,
    max_airtime_percent: 80,
    switch_threshold: 10,
    cooldown: 30,
};

const DEVICE_TYPES = [
    "Smartphone",
    "Tablet",
    "PC",
    "Laptop/Desktop",
    "TV/Streaming",
    "Printer",
    "IoT",
    "Camera",
    "Robot",
    "Router",
    "Unknown",
];

const PRIORITIES = [
    "critical",
    "high",
    "medium",
    "low",
];

const BAND_LABELS = {
    "2G": "2.4 GHz",
    "5G": "5 GHz",
    "6G": "6 GHz",
};

const cloneRule = (rule) =>
    JSON.parse(JSON.stringify(rule));

/*
 * ============================================================
 * AUTOMATIC WEIGHT DERIVATION
 * ============================================================
 *
 * The client provides requirements:
 *
 * - preferred band
 * - RSSI thresholds
 * - minimum throughput
 * - maximum airtime
 * - device type
 * - priority
 *
 * The algorithm converts these requirements into weights.
 *
 * The final weights ALWAYS sum to 1.0.
 * ============================================================
 */
const deriveWeights = (rule) => {
    const weights = {
        clients: 0.20,
        rssi: 0.20,
        airtime: 0.20,
        throughput: 0.20,
        txpower: 0.20,
    };

    /*
     * --------------------------------------------------------
     * RSSI importance
     * --------------------------------------------------------
     *
     * A stricter RSSI requirement means that signal quality
     * becomes more important.
     */
    const rssiValues = ["2G", "5G", "6G"]
        .filter((band) => rule.bands?.[band])
        .map((band) =>
            Number(
                rule.thresholds?.[band]?.min_rssi ?? -70
            )
        );

    if (rssiValues.length > 0) {
        const strictestRssi = Math.max(...rssiValues);

        if (strictestRssi >= -60) {
            weights.rssi += 0.25;
        } else if (strictestRssi >= -65) {
            weights.rssi += 0.20;
        } else if (strictestRssi >= -70) {
            weights.rssi += 0.10;
        }
    }

    /*
     * --------------------------------------------------------
     * Throughput importance
     * --------------------------------------------------------
     */
    const throughput = Number(
        rule.min_throughput_mbps || 0
    );

    if (throughput >= 100) {
        weights.throughput += 0.30;
    } else if (throughput >= 50) {
        weights.throughput += 0.25;
    } else if (throughput >= 20) {
        weights.throughput += 0.15;
    } else if (throughput >= 10) {
        weights.throughput += 0.08;
    }

    /*
     * --------------------------------------------------------
     * Airtime importance
     * --------------------------------------------------------
     *
     * A lower allowed airtime means that congestion avoidance
     * is more important.
     */
    const maxAirtime = Number(
        rule.max_airtime_percent ?? 80
    );

    if (maxAirtime <= 40) {
        weights.airtime += 0.30;
    } else if (maxAirtime <= 50) {
        weights.airtime += 0.25;
    } else if (maxAirtime <= 60) {
        weights.airtime += 0.15;
    } else if (maxAirtime <= 70) {
        weights.airtime += 0.08;
    }

    /*
     * --------------------------------------------------------
     * Preferred band
     * --------------------------------------------------------
     *
     * The preferred band influences the decision indirectly.
     * We give more importance to signal/throughput because
     * those metrics are normally decisive for band selection.
     */
    if (rule.preferred_band === "6G") {
        weights.throughput += 0.10;
        weights.rssi += 0.05;
    } else if (rule.preferred_band === "5G") {
        weights.throughput += 0.08;
        weights.rssi += 0.04;
    } else if (rule.preferred_band === "2G") {
        weights.clients += 0.08;
        weights.airtime += 0.04;
    }

    /*
     * --------------------------------------------------------
     * Device type
     * --------------------------------------------------------
     */
    switch (rule.device_type) {
        case "TV/Streaming":
            weights.throughput += 0.15;
            weights.airtime += 0.05;
            break;

        case "Camera":
            weights.throughput += 0.10;
            weights.rssi += 0.10;
            break;

        case "Smartphone":
        case "Tablet":
            weights.rssi += 0.05;
            weights.throughput += 0.05;
            break;

        case "PC":
        case "Laptop/Desktop":
            weights.throughput += 0.10;
            weights.rssi += 0.05;
            break;

        case "IoT":
        case "Printer":
        case "Robot":
            weights.rssi += 0.05;
            weights.clients += 0.05;
            break;

        case "Router":
            weights.airtime += 0.10;
            weights.clients += 0.05;
            break;

        default:
            break;
    }

    /*
     * --------------------------------------------------------
     * Priority
     * --------------------------------------------------------
     */
    switch (rule.priority) {
        case "critical":
            weights.rssi += 0.10;
            weights.throughput += 0.10;
            weights.airtime += 0.05;
            break;

        case "high":
            weights.rssi += 0.07;
            weights.throughput += 0.07;
            weights.airtime += 0.03;
            break;

        case "low":
            weights.clients += 0.05;
            weights.txpower += 0.05;
            break;

        case "medium":
        default:
            break;
    }

    /*
     * --------------------------------------------------------
     * Normalize
     * --------------------------------------------------------
     */
    const total = Object.values(weights).reduce(
        (sum, value) => sum + value,
        0
    );

    Object.keys(weights).forEach((key) => {
        weights[key] = Number(
            (weights[key] / total).toFixed(4)
        );
    });

    /*
     * Correct rounding so that total is exactly 1.0.
     */
    const normalizedTotal = Object.values(weights).reduce(
        (sum, value) => sum + value,
        0
    );

    const correction = Number(
        (1 - normalizedTotal).toFixed(4)
    );

    weights.throughput = Number(
        (weights.throughput + correction).toFixed(4)
    );

    return weights;
};

/*
 * Merge server rule with defaults.
 */
const mergeRule = (rule) => {
    const result = cloneRule(DEFAULT_RULE);

    if (!rule) {
        return result;
    }

    result.device_type =
        rule.device_type ?? result.device_type;

    result.priority =
        rule.priority ?? result.priority;

    result.preferred_band =
        rule.preferred_band ?? result.preferred_band;

    result.min_throughput_mbps = Number(
        rule.min_throughput_mbps ??
            result.min_throughput_mbps
    );

    result.max_airtime_percent = Number(
        rule.max_airtime_percent ??
            result.max_airtime_percent
    );

    result.switch_threshold = Number(
        rule.switch_threshold ??
            result.switch_threshold
    );

    result.cooldown = Number(
        rule.cooldown ??
            result.cooldown
    );

    result.bands = {
        ...result.bands,
        ...(rule.bands || {}),
    };

    result.weights = {
        ...result.weights,
        ...(rule.weights || {}),
    };

    result.thresholds = {
        ...result.thresholds,
        ...(rule.thresholds || {}),
    };

    ["2G", "5G", "6G"].forEach((band) => {
        result.thresholds[band] = {
            ...DEFAULT_RULE.thresholds[band],
            ...(rule.thresholds?.[band] || {}),
        };
    });

    return result;
};

const Configuration = () => {
    const [devices, setDevices] = useState([]);
    const [selectedMac, setSelectedMac] = useState("");

    const [rule, setRule] = useState(
        cloneRule(DEFAULT_RULE)
    );

    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");

    const selectedDevice = useMemo(
        () =>
            devices.find(
                (device) =>
                    device.mac === selectedMac
            ),
        [devices, selectedMac]
    );

    /*
     * Automatically derive weights whenever the user
     * changes the configuration.
     */
    useEffect(() => {
        setRule((current) => ({
            ...current,
            weights: deriveWeights(current),
        }));
    }, [
        rule.device_type,
        rule.priority,
        rule.preferred_band,
        rule.min_throughput_mbps,
        rule.max_airtime_percent,
        rule.thresholds,
        rule.bands,
    ]);

    const loadData = async () => {
        try {
            setLoading(true);
            setError("");

            const [
                devicesResponse,
                rulesResponse,
            ] = await Promise.all([
                fetch(`${API_URL}/api/devices`),
                fetch(`${API_URL}/api/device-rules`),
            ]);

            if (!devicesResponse.ok) {
                throw new Error(
                    `Devices API: HTTP ${devicesResponse.status}`
                );
            }

            if (!rulesResponse.ok) {
                throw new Error(
                    `Rules API: HTTP ${rulesResponse.status}`
                );
            }

            const devicesData =
                await devicesResponse.json();

            const rulesData =
                await rulesResponse.json();

            const rawDevices =
                Array.isArray(devicesData)
                    ? devicesData
                    : devicesData.devices || [];

            const normalized = rawDevices
                .filter(
                    (device) => device?.mac
                )
                .map((device) => ({
                    ...device,
                    mac: String(device.mac)
                        .trim()
                        .toLowerCase()
                        .replace(/-/g, ":"),
                }));

            setDevices(normalized);

            if (normalized.length > 0) {
                setSelectedMac(
                    normalized[0].mac
                );
            }

            const rules =
                rulesData?.rules || {};

            if (
                normalized.length > 0 &&
                rules[normalized[0].mac]
            ) {
                const loadedRule = mergeRule(
                    rules[normalized[0].mac]
                );

                loadedRule.weights =
                    deriveWeights(loadedRule);

                setRule(loadedRule);
            } else {
                const defaultRule =
                    cloneRule(DEFAULT_RULE);

                defaultRule.weights =
                    deriveWeights(defaultRule);

                setRule(defaultRule);
            }
        } catch (err) {
            console.error(err);

            setError(
                err?.message ||
                    "Unable to load configuration."
            );
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, []);

    const loadSelectedRule = async (mac) => {
        try {
            setError("");

            const response = await fetch(
                `${API_URL}/api/device-rules/${encodeURIComponent(
                    mac
                )}`
            );

            if (!response.ok) {
                throw new Error(
                    `HTTP ${response.status}`
                );
            }

            const data =
                await response.json();

            const loadedRule = mergeRule(
                data.rule
            );

            loadedRule.weights =
                deriveWeights(loadedRule);

            setRule(loadedRule);
        } catch (err) {
            console.error(err);

            const defaultRule =
                cloneRule(DEFAULT_RULE);

            defaultRule.weights =
                deriveWeights(defaultRule);

            setRule(defaultRule);

            setError(
                `Unable to load rule for ${mac}. Default rule loaded.`
            );
        }
    };

    const handleDeviceChange = async (event) => {
        const mac = event.target.value;

        setSelectedMac(mac);

        const device = devices.find(
            (item) =>
                item.mac === mac
        );

        const nextRule =
            cloneRule(DEFAULT_RULE);

        if (device?.type) {
            nextRule.device_type =
                device.type;
        }

        if (device?.priority) {
            nextRule.priority =
                device.priority;
        }

        nextRule.weights =
            deriveWeights(nextRule);

        setRule(nextRule);

        await loadSelectedRule(mac);
    };

    const updateRule = (path, value) => {
        setRule((current) => {
            const next = cloneRule(current);

            let target = next;

            for (
                let i = 0;
                i < path.length - 1;
                i += 1
            ) {
                target =
                    target[path[i]];
            }

            target[
                path[path.length - 1]
            ] = value;

            /*
             * Recalculate weights immediately after
             * any user preference changes.
             */
            next.weights =
                deriveWeights(next);

            return next;
        });

        setSuccess("");
        setError("");
    };

    const totalWeight = Object.values(
        rule.weights || {}
    ).reduce(
        (sum, value) =>
            sum + Number(value || 0),
        0
    );

    const weightIsValid =
        Math.abs(
            totalWeight - 1
        ) < 0.001;

    const enabledBands = Object.entries(
        rule.bands || {}
    )
        .filter(([, enabled]) => enabled)
        .map(([band]) => band);

    const saveRule = async () => {
        try {
            setSaving(true);
            setError("");
            setSuccess("");

            if (!selectedMac) {
                throw new Error(
                    "Select a device first."
                );
            }

            if (!weightIsValid) {
                throw new Error(
                    "Unable to generate valid optimization weights."
                );
            }

            if (
                enabledBands.length === 0
            ) {
                throw new Error(
                    "Enable at least one Wi-Fi band."
                );
            }

            if (
                !enabledBands.includes(
                    rule.preferred_band
                )
            ) {
                throw new Error(
                    "Preferred band must be enabled."
                );
            }

            /*
             * Always derive weights one final time before
             * sending the rule to the backend.
             */
            const finalRule = {
                ...rule,
                weights: deriveWeights(rule),
            };

            const response = await fetch(
                `${API_URL}/api/device-rules/${encodeURIComponent(
                    selectedMac
                )}`,
                {
                    method: "PUT",
                    headers: {
                        "Content-Type":
                            "application/json",
                        Accept:
                            "application/json",
                    },
                    body: JSON.stringify(
                        finalRule
                    ),
                }
            );

            const data =
                await response.json();

            if (!response.ok) {
                throw new Error(
                    data?.error ||
                        `HTTP ${response.status}`
                );
            }

            const savedRule = mergeRule(
                data.rule
            );

            /*
             * Display the automatically derived
             * weights after saving.
             */
            savedRule.weights =
                deriveWeights(savedRule);

            setRule(savedRule);

            setSuccess(
                "Device optimization rule saved successfully."
            );
        } catch (err) {
            console.error(err);

            setError(
                err?.message ||
                    "Unable to save rule."
            );
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <Box m="20px">
                <Header
                    title="DEVICES CONFIGURATION"
                    subtitle="Per-device multi-metric Wi-Fi optimization"
                />

                <Box
                    display="flex"
                    justifyContent="center"
                    mt="50px"
                >
                    <CircularProgress />
                </Box>
            </Box>
        );
    }

    return (
        <Box m="20px">
            <Header
                title="DEVICE CONFIGURATION"
                subtitle="Configure device requirements. The controller automatically derives optimization weights."
            />

            {error && (
                <Alert
                    severity="error"
                    sx={{ mb: 2 }}
                    onClose={() =>
                        setError("")
                    }
                >
                    {error}
                </Alert>
            )}

            {/* DEVICE POLICY */}
            <Paper
                sx={{
                    p: 3,
                    mb: 3,
                }}
            >
                <Box
                    display="flex"
                    alignItems="center"
                    gap={1}
                    mb={2}
                >
                    <SettingsOutlinedIcon />

                    <Typography variant="h5">
                        Device policy
                    </Typography>
                </Box>

                <Grid
                    container
                    spacing={2}
                >
                    <Grid item xs={12} md={7}>
                        <FormControl
                            fullWidth
                            variant="filled"
                        >
                            <InputLabel>
                                Device
                            </InputLabel>

                            <Select
                                value={
                                    selectedMac
                                }
                                label="Device"
                                onChange={
                                    handleDeviceChange
                                }
                            >
                                {devices.map(
                                    (device) => (
                                        <MenuItem
                                            key={
                                                device.mac
                                            }
                                            value={
                                                device.mac
                                            }
                                        >
                                            {device.hostname ||
                                                "Unknown device"}{" "}
                                            —{" "}
                                            {
                                                device.mac
                                            }
                                        </MenuItem>
                                    )
                                )}
                            </Select>
                        </FormControl>
                    </Grid>

                    <Grid item xs={12} md={5}>
                        <Typography
                            variant="body2"
                            sx={{
                                opacity: 0.7,
                                mb: 0.5,
                            }}
                        >
                            Current device
                        </Typography>

                        <Typography fontWeight="bold">
                            {selectedDevice?.hostname ||
                                "Unknown device"}
                        </Typography>

                        <Typography variant="body2">
                            Type:{" "}
                            {selectedDevice?.type ||
                                rule.device_type}
                        </Typography>

                        <Typography variant="body2">
                            Current band:{" "}
                            {selectedDevice?.band ||
                                "N/A"}
                        </Typography>
                    </Grid>
                </Grid>
            </Paper>

            {/* DEVICE CLASSIFICATION */}
            <Paper sx={{ p: 3, mb: 3 }}>
                <Typography
                    variant="h6"
                    gutterBottom
                >
                    Device classification
                </Typography>

                <Grid
                    container
                    spacing={2}
                >
                    <Grid item xs={12} md={6}>
                        <FormControl
                            fullWidth
                            variant="filled"
                        >
                            <InputLabel>
                                Device Type
                            </InputLabel>

                            <Select
                                value={
                                    rule.device_type
                                }
                                label="Device Type"
                                onChange={(event) =>
                                    updateRule(
                                        [
                                            "device_type",
                                        ],
                                        event.target
                                            .value
                                    )
                                }
                            >
                                {DEVICE_TYPES.map(
                                    (type) => (
                                        <MenuItem
                                            key={type}
                                            value={type}
                                        >
                                            {type}
                                        </MenuItem>
                                    )
                                )}
                            </Select>
                        </FormControl>
                    </Grid>

                    <Grid item xs={12} md={6}>
                        <FormControl
                            fullWidth
                            variant="filled"
                        >
                            <InputLabel>
                                Priority
                            </InputLabel>

                            <Select
                                value={
                                    rule.priority
                                }
                                label="Priority"
                                onChange={(event) =>
                                    updateRule(
                                        [
                                            "priority",
                                        ],
                                        event.target
                                            .value
                                    )
                                }
                            >
                                {PRIORITIES.map(
                                    (priority) => (
                                        <MenuItem
                                            key={
                                                priority
                                            }
                                            value={
                                                priority
                                            }
                                        >
                                            {priority
                                                .charAt(
                                                    0
                                                )
                                                .toUpperCase() +
                                                priority.slice(
                                                    1
                                                )}
                                        </MenuItem>
                                    )
                                )}
                            </Select>
                        </FormControl>
                    </Grid>
                </Grid>
            </Paper>

            {/* BAND SELECTION */}
            <Paper sx={{ p: 3, mb: 3 }}>
                <Typography
                    variant="h6"
                    gutterBottom
                >
                    Band selection
                </Typography>

                <Grid
                    container
                    spacing={2}
                >
                    {["2G", "5G", "6G"].map(
                        (band) => (
                            <Grid
                                item
                                xs={12}
                                md={4}
                                key={band}
                            >
                                <FormControlLabel
                                    control={
                                        <Checkbox
                                            checked={
                                                !!rule
                                                    .bands[
                                                    band
                                                ]
                                            }
                                            onChange={(
                                                event
                                            ) =>
                                                updateRule(
                                                    [
                                                        "bands",
                                                        band,
                                                    ],
                                                    event
                                                        .target
                                                        .checked
                                                )
                                            }
                                        />
                                    }
                                    label={
                                        BAND_LABELS[
                                            band
                                        ]
                                    }
                                />

                                <TextField
                                    fullWidth
                                    type="number"
                                    label="Minimum RSSI (dBm)"
                                    value={
                                        rule
                                            .thresholds[
                                            band
                                        ]
                                            .min_rssi
                                    }
                                    onChange={(event) =>
                                        updateRule(
                                            [
                                                "thresholds",
                                                band,
                                                "min_rssi",
                                            ],
                                            Number(
                                                event
                                                    .target
                                                    .value
                                            )
                                        )
                                    }
                                    helperText="Band is rejected below this RSSI"
                                    variant="filled"
                                    sx={{ mt: 1 }}
                                />
                            </Grid>
                        )
                    )}
                </Grid>

                <Divider sx={{ my: 3 }} />

                <FormControl
                    fullWidth
                    variant="filled"
                >
                    <InputLabel>
                        Preferred Band
                    </InputLabel>

                    <Select
                        value={
                            rule.preferred_band
                        }
                        label="Preferred Band"
                        onChange={(event) =>
                            updateRule(
                                [
                                    "preferred_band",
                                ],
                                event.target.value
                            )
                        }
                    >
                        {["2G", "5G", "6G"].map(
                            (band) => (
                                <MenuItem
                                    key={band}
                                    value={band}
                                    disabled={
                                        !rule.bands[
                                            band
                                        ]
                                    }
                                >
                                    {
                                        BAND_LABELS[
                                            band
                                        ]
                                    }
                                </MenuItem>
                            )
                        )}
                    </Select>
                </FormControl>
            </Paper>

            {/* PERFORMANCE CONSTRAINTS */}
            <Paper sx={{ p: 3, mb: 3 }}>
                <Typography
                    variant="h6"
                    gutterBottom
                >
                    Performance constraints
                </Typography>

                <Grid
                    container
                    spacing={2}
                >
                    <Grid item xs={12} md={4}>
                        <TextField
                            fullWidth
                            type="number"
                            label="Minimum throughput (Mbps)"
                            value={
                                rule.min_throughput_mbps
                            }
                            onChange={(event) =>
                                updateRule(
                                    [
                                        "min_throughput_mbps",
                                    ],
                                    Number(
                                        event.target
                                            .value
                                    )
                                )
                            }
                            variant="filled"
                        />
                    </Grid>

                    <Grid item xs={12} md={4}>
                        <TextField
                            fullWidth
                            type="number"
                            label="Maximum airtime (%)"
                            value={
                                rule.max_airtime_percent
                            }
                            onChange={(event) =>
                                updateRule(
                                    [
                                        "max_airtime_percent",
                                    ],
                                    Number(
                                        event.target
                                            .value
                                    )
                                )
                            }
                            variant="filled"
                        />
                    </Grid>

                    <Grid item xs={12} md={4}>
                        <TextField
                            fullWidth
                            type="number"
                            label="Switch threshold (score points)"
                            value={
                                rule.switch_threshold
                            }
                            onChange={(event) =>
                                updateRule(
                                    [
                                        "switch_threshold",
                                    ],
                                    Number(
                                        event.target
                                            .value
                                    )
                                )
                            }
                            variant="filled"
                        />
                    </Grid>

                    <Grid item xs={12} md={4}>
                        <TextField
                            fullWidth
                            type="number"
                            label="Cooldown (seconds)"
                            value={
                                rule.cooldown
                            }
                            onChange={(event) =>
                                updateRule(
                                    ["cooldown"],
                                    Number(
                                        event.target
                                            .value
                                    )
                                )
                            }
                            variant="filled"
                        />
                    </Grid>
                </Grid>
            {/* AUTOMATIC WEIGHTS */}
            <Paper sx={{ p: 3, mb: 3 }}>
                <Box
                    display="flex"
                    alignItems="center"
                    gap={1}
                    mb={1}
                >
                    <AutoAwesomeOutlinedIcon />

                    <Typography variant="h6">
                        Automatically derived optimization weights
                    </Typography>
                </Box>

                <Typography
                    variant="body2"
                    sx={{
                        opacity: 0.7,
                        mb: 3,
                    }}
                >
                    The weights are automatically calculated
                    from the device requirements above. You
                    do not need to configure them manually.
                </Typography>

                <Grid
                    container
                    spacing={2}
                >
                    {[
                        ["rssi", "RSSI"],
                        ["airtime", "Airtime"],
                        [
                            "throughput",
                            "Throughput",
                        ],
                        [
                            "clients",
                            "Client load",
                        ],
                        ["txpower", "TX power"],
                    ].map(
                        ([key, label]) => (
                            <Grid
                                item
                                xs={12}
                                sm={6}
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
                                        variant="body2"
                                        sx={{
                                            opacity: 0.7,
                                        }}
                                    >
                                        {label}
                                    </Typography>

                                    <Typography
                                        variant="h4"
                                        fontWeight="bold"
                                    >
                                        {Math.round(
                                            Number(
                                                rule
                                                    .weights[
                                                    key
                                                ]
                                            ) * 100
                                        )}
                                        %
                                    </Typography>
                                </Paper>
                            </Grid>
                        )
                    )}
                </Grid>

                <Alert
                    severity={
                        weightIsValid
                            ? "success"
                            : "warning"
                    }
                    sx={{ mt: 3 }}
                >
                    Automatically derived total:{" "}
                    {(totalWeight * 100).toFixed(
                        0
                    )}
                    %
                </Alert>
            </Paper>

            </Paper>

            {/* SAVE */}
            <Box
                display="flex"
                justifyContent="flex-end"
                mb={4}
            >
                <Button
                    variant="contained"
                    color="secondary"
                    size="large"
                    startIcon={
                        saving ? (
                            <CircularProgress
                                size={20}
                            />
                        ) : (
                            <SaveOutlinedIcon />
                        )
                    }
                    onClick={saveRule}
                    disabled={
                        saving ||
                        !selectedMac
                    }
                    sx={{
                        minWidth: 240,
                        height: 50,
                    }}
                >
                    {saving
                        ? "Saving..."
                        : "Save Device Rule"}
                </Button>
            </Box>

            <Snackbar
                open={!!success}
                autoHideDuration={4000}
                onClose={() =>
                    setSuccess("")
                }
                message={success}
            />
        </Box>
    );
};

export default Configuration;
