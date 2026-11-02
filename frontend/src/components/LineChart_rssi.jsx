import { useEffect, useMemo, useState } from "react";
import {
    ResponsiveContainer,
    LineChart as RechartsLineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
} from "recharts";

import {
    Box,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    Typography,
    Alert,
    Chip,
    Stack,
} from "@mui/material";

const API_URL = "/api/rssi";
const MAX_POINTS = 5000;

// Palette de couleurs distinctes.
const LINE_COLORS = [
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#CC79A7",
    "#E69F00",
    "#56B4E9",
    "#000000",
    "#7B2CBF",
    "#E63946",
    "#2A9D8F",
    "#6A994E",
    "#F72585",
    "#4361EE",
    "#9C6644",
    "#7209B7",
    "#3A86FF",
    "#FB5607",
    "#588157",
    "#277DA1",
    "#BC6C25",
    "#6D597A",
    "#C1121F",
    "#386641",
    "#4895EF",
    "#B56576",
    "#577590",
    "#A44A3F",
    "#008080",
    "#AD5D00",
    "#5F0F40",
];

// Styles de lignes : continu, tirets, pointillés, etc.
const LINE_DASHES = [
    undefined,
    "8 4",
    "2 4",
    "2 3 8 3",
    "12 5",
    "12 4 2 4",
];

const getLineColor = (index) =>
    LINE_COLORS[index % LINE_COLORS.length];

const getLineDash = (index) =>
    LINE_DASHES[index % LINE_DASHES.length];

// Légende personnalisée et interactive.
function CustomLegend({
    lineKeys,
    hiddenLines,
    onToggle,
    onShowAll,
    onHideAll,
}) {
    return (
        <Box sx={{ px: 1, pt: 1 }}>
            <Stack
                direction="row"
                spacing={1}
                useFlexGap
                flexWrap="wrap"
                alignItems="center"
                sx={{ mb: 1 }}
            >
                <Typography
                    variant="caption"
                    color="text.secondary"
                >
                    {lineKeys.length} Lines(s) — Choose a Line chart to display or hide.
                    </Typography>

                <Chip
                    size="small"
                    label="Display All"
                    clickable
                    onClick={onShowAll}
                />

                <Chip
                    size="small"
                    label="Hide All"
                    clickable
                    onClick={onHideAll}
                />
            </Stack>

            <Stack
                direction="row"
                spacing={0.75}
                useFlexGap
                flexWrap="wrap"
                sx={{
                    maxHeight: 155,
                    overflowY: "auto",
                    alignContent: "flex-start",
                    pr: 0.5,
                }}
            >
                {lineKeys.map((key, index) => {
                    const hidden = hiddenLines.includes(key);
                    const color = getLineColor(index);
                    const dash = getLineDash(index);

                    return (
                        <Chip
                            key={key}
                            clickable
                            onClick={() => onToggle(key)}
                            variant={hidden ? "outlined" : "filled"}
                            title={
                                hidden
                                    ? "Afficher cette courbe"
                                    : "Masquer cette courbe"
                            }
                            icon={
                                <Box
                                    component="span"
                                    sx={{
                                        display: "inline-block",
                                        width: 22,
                                        height: 0,
                                        borderTop: `3px ${
                                            dash
                                                ? "dashed"
                                                : "solid"
                                        } ${color}`,
                                        opacity: hidden ? 0.4 : 1,
                                    }}
                                />
                            }
                            label={key}
                            sx={{
                                opacity: hidden ? 0.55 : 1,
                                maxWidth: "100%",
                                "& .MuiChip-label": {
                                    display: "block",
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                    whiteSpace: "nowrap",
                                    maxWidth: {
                                        xs: 180,
                                        sm: 260,
                                    },
                                    fontSize: "0.75rem",
                                },
                                "& .MuiChip-icon": {
                                    ml: 1,
                                    mr: -0.25,
                                },
                            }}
                        />
                    );
                })}
            </Stack>
        </Box>
    );
}

const LineChart = () => {
    const [measurements, setMeasurements] = useState([]);
    const [selectedStation, setSelectedStation] =
        useState("all");
    const [hiddenLines, setHiddenLines] = useState([]);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(true);

    // Récupération périodique des mesures RSSI.
    useEffect(() => {
        let mounted = true;
        let inProgress = false;

        const fetchRSSI = async () => {
            if (inProgress) return;

            inProgress = true;

            try {
                const response = await fetch(API_URL, {
                    headers: {
                        Accept: "application/json",
                    },
                });

                const contentType =
                    response.headers.get("content-type") || "";

                if (!response.ok) {
                    throw new Error(
                        `Erreur HTTP ${response.status}`
                    );
                }

                if (!contentType.includes("application/json")) {
                    const body = await response.text();

                    throw new Error(
                        `Réponse non JSON : ${body.slice(0, 150)}`
                    );
                }

                const data = await response.json();

                const incoming = Array.isArray(data)
                    ? data
                    : data.measurements;

                if (!Array.isArray(incoming)) {
                    throw new Error(
                        "API must send measurements."
                    );
                }

                if (mounted) {
                    setMeasurements((previous) => {
                        const merged = new Map();

                        for (const item of [
                            ...previous,
                            ...incoming,
                        ]) {
                            const key = [
                                item.timestamp,
                                item.mac,
                                item.interface,
                            ].join("_");

                            merged.set(key, item);
                        }

                        return [...merged.values()]
                            .sort(
                                (a, b) =>
                                    Number(a.timestamp) -
                                    Number(b.timestamp)
                            )
                            .slice(-MAX_POINTS);
                    });

                    setError("");
                    setLoading(false);
                }
            } catch (err) {
                if (mounted) {
                    setError(
                        "Impossible de récupérer les mesures RSSI : " +
                            (err instanceof Error
                                ? err.message
                                : String(err))
                    );

                    setLoading(false);
                }

                console.error("Erreur API RSSI :", err);
            } finally {
                inProgress = false;
            }
        };

        fetchRSSI();

        const interval = setInterval(fetchRSSI, 2000);

        return () => {
            mounted = false;
            clearInterval(interval);
        };
    }, []);

    // Liste des stations détectées.
    const stations = useMemo(() => {
        return [
            ...new Set(
                measurements
                    .map((item) => item.mac)
                    .filter(Boolean)
            ),
        ].sort();
    }, [measurements]);

    // Filtrage des mesures selon la station.
    const filteredMeasurements = useMemo(() => {
        if (selectedStation === "all") {
            return measurements;
        }

        return measurements.filter(
            (item) => item.mac === selectedStation
        );
    }, [measurements, selectedStation]);

    // Liste des interfaces disponibles.
    const interfaces = useMemo(() => {
        return [
            ...new Set(
                filteredMeasurements
                    .map((item) => item.interface)
                    .filter(Boolean)
            ),
        ].sort();
    }, [filteredMeasurements]);

    // Préparation des données du graphique.
    const { chartData, lineKeys } = useMemo(() => {
        const grouped = new Map();
        const keys = new Set();

        for (const item of filteredMeasurements) {
            const timestamp = Number(item.timestamp);

            const milliseconds =
                timestamp < 1e12
                    ? timestamp * 1000
                    : timestamp;

            const date = new Date(milliseconds);

            if (
                !Number.isFinite(timestamp) ||
                Number.isNaN(date.getTime()) ||
                !item.mac ||
                !item.interface
            ) {
                continue;
            }

            const timeKey = String(timestamp);

            if (!grouped.has(timeKey)) {
                grouped.set(timeKey, {
                    timestamp,
                    time: date.toLocaleTimeString("fr-FR", {
                        hour: "2-digit",
                        minute: "2-digit"
                    }),
                });
            }

            const lineKey =
                `${item.mac} | ${item.interface}`;

            const rssi = Number(item.rssi);

            grouped.get(timeKey)[lineKey] =
                Number.isFinite(rssi) ? rssi : null;

            keys.add(lineKey);
        }

        return {
            chartData: [...grouped.values()].sort(
                (a, b) => a.timestamp - b.timestamp
            ),
            lineKeys: [...keys].sort(),
        };
    }, [filteredMeasurements]);

    // Réinitialiser la légende lors du changement de station.
    useEffect(() => {
        setHiddenLines([]);
    }, [selectedStation]);

    // Afficher ou masquer une courbe.
    const toggleLine = (key) => {
        setHiddenLines((previous) =>
            previous.includes(key)
                ? previous.filter((item) => item !== key)
                : [...previous, key]
        );
    };

    const showAllLines = () => {
        setHiddenLines([]);
    };

    const hideAllLines = () => {
        setHiddenLines(lineKeys);
    };

    return (
        <Box
            height="100%"
            width="100%"
            display="flex"
            flexDirection="column"
            gap={2}
        >
            {/* En-tête et filtre des stations */}
            <Box
                display="flex"
                justifyContent="space-between"
                alignItems="center"
                flexWrap="wrap"
                gap={2}
            >
                <Box>
                    <Typography variant="h5">
        RSSI Evolution per station
                    </Typography>

                    <Typography
                        variant="body2"
                        color="text.secondary"
                    >
                        Tri-band steering monitoring
                    </Typography>
                </Box>

                <FormControl
                    size="small"
                    sx={{ minWidth: 260 }}
                >
                    <InputLabel id="station-select-label">
                      Wi-Fi   Stations 
                    </InputLabel>

                    <Select
                        labelId="station-select-label"
                        value={selectedStation}
                        label="Stations Wi-Fi"
                        onChange={(event) =>
                            setSelectedStation(event.target.value)
                        }
                    >
                        <MenuItem value="all">
                            All stations
                        </MenuItem>

                        {stations.map((mac) => (
                            <MenuItem key={mac} value={mac}>
                                {mac}
                            </MenuItem>
                        ))}
                    </Select>
                </FormControl>
            </Box>

            {/* Messages d'état */}
            {error && (
                <Alert severity="error">
                    {error}
                </Alert>
            )}

            {loading && (
                <Alert severity="info">
                    Connexion to RSSI API...
                </Alert>
            )}

            {!loading &&
                !error &&
                filteredMeasurements.length === 0 && (
                    <Alert severity="info">
                        En attente des premières mesures RSSI
                        pour cette sélection.
                    </Alert>
                )}

            {/* Graphique RSSI */}
            <Box
                flex={1}
                minHeight={400}
                width="100%"
            >
                <ResponsiveContainer
                    width="100%"
                    height="100%"
                >
                    <RechartsLineChart
                        data={chartData}
                        margin={{
                            top: 15,
                            right: 25,
                            left: 15,
                            bottom: 10,
                        }}
                    >
                        <CartesianGrid
                            strokeDasharray="3 3"
                            opacity={0.25}
                        />

                        <XAxis
                            dataKey="time"
                            minTickGap={35}
                            tick={{ fontSize: 11 }}
                        />

                        <YAxis
                            tickCount={10}
                            tick={{ fontSize: 12 }}
                            tickFormatter={(value) =>
                                `${value} dBm`
                            }
                            domain={[-100, -30]}
                            ticks={[
                                -100, -95, -90, -85, -80,
                                -75, -70, -65, -60, -55,
                                -50, -45, -40, -35, -30,
                            ]}
                        />

                        <Tooltip
                            labelFormatter={(label) =>
                                `Heure : ${label}`
                            }
                            formatter={(value, name) => [
                                value == null
                                    ? "—"
                                    : `${value} dBm`,
                                name,
                            ]}
                            contentStyle={{
                                borderRadius: 8,
                                fontSize: 12,
                                maxHeight: 250,
                                overflowY: "auto",
                            }}
                        />

                        {lineKeys.map((key, index) => (
                            <Line
                                key={key}
                                type="monotone"
                                dataKey={key}
                                name={key}
                                connectNulls={false}
                                dot={false}
                                activeDot={{ r: 4 }}
                                stroke={getLineColor(index)}
                                strokeDasharray={getLineDash(index)}
                                strokeWidth={2}
                                hide={hiddenLines.includes(key)}
                                isAnimationActive={false}
                            />
                        ))}
                    </RechartsLineChart>
                </ResponsiveContainer>
            </Box>

            {/* Légende interactive */}
            {lineKeys.length > 0 && (
                <CustomLegend
                    lineKeys={lineKeys}
                    hiddenLines={hiddenLines}
                    onToggle={toggleLine}
                    onShowAll={showAllLines}
                    onHideAll={hideAllLines}
                />
            )}

            {/* Statistiques */}
            <Typography
                variant="caption"
                color="text.secondary"
            >
                {measurements.length} mesure(s) en mémoire ·{" "}
                {stations.length} station(s) ·{" "}
                {interfaces.length} interface(s) ·{" "}
                {lineKeys.length - hiddenLines.length} courbe(s)
                visible(s)
            </Typography>
        </Box>
    );
};

export default LineChart;
