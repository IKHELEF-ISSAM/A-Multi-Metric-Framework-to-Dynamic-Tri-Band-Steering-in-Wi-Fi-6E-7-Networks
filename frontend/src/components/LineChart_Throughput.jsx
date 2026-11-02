import { useEffect, useMemo, useState } from "react";
import { Button } from "@mui/material";
import * as XLSX from "xlsx";

import {
    ResponsiveContainer,
    LineChart as RechartsLineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
} from "recharts";

import {
    Box,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    Typography,
    Alert,
} from "@mui/material";

const API_URL = "/api/throughput";

const MAX_POINTS = 50000;

const lineColors = [
    "#1976d2",
    "#e53935",
    "#43a047",
    "#8e24aa",
    "#fb8c00",
    "#00897b",
    "#6d4c41",
    "#3949ab",
    "#00acc1",
    "#f4511e",
    "#7cb342",
    "#d81b60",
    "#5e35b1",
    "#039be5",
    "#c0ca33",
    "#8d6e63",
    "#546e7a",
    "#ffb300",
    "#26a69a",
    "#ec407a",
    "#9c27b0",
    "#2e7d32",
    "#ef6c00",
    "#0277bd",
    "#c62828",
    "#558b2f",
    "#ad1457",
    "#4527a0",
    "#00838f",
];

const LineChartThroughput = () => {
    const [measurements, setMeasurements] = useState([]);
    const [selectedStation, setSelectedStation] = useState("all");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(true);
    const handleExportExcel = () => {
    if (measurements.length === 0) {
        setError("Aucune mesure de throughput à exporter.");
        return;
    }

    const bandMapping = {
        ph0: "2.4 GHz",
        "ph0.1": "5 GHz",
        "ph0.2": "6 GHz",
    };

    const rows = measurements
        .map((item) => {
            const timestamp = Number(item.timestamp);

            const milliseconds =
                timestamp < 1e12
                    ? timestamp * 1000
                    : timestamp;

            const date = new Date(milliseconds);

            return {
                "Date et heure": Number.isNaN(date.getTime())
                    ? ""
                    : date.toLocaleString("fr-FR"),

                "Station MAC": item.mac ?? "",

                "Interface Wi-Fi": item.interface ?? "",

                "Frequency Band":
                    bandMapping[item.interface] ?? "Unknown band",

                "Throughput (Mbps)": Number(item.throughput_mbps),
            };
        })
        .filter((row) =>
            Number.isFinite(row["Throughput (Mbps)"])
        );

    if (rows.length === 0) {
        setError("Aucune mesure de throughput valide à exporter.");
        return;
    }

    const worksheet = XLSX.utils.json_to_sheet(rows);

    worksheet["!cols"] = [
        { wch: 22 },
        { wch: 22 },
        { wch: 20 },
        { wch: 20 },
        { wch: 22 },
    ];

    const workbook = XLSX.utils.book_new();

    XLSX.utils.book_append_sheet(
        workbook,
        worksheet,
        "Throughput"
    );

    const now = new Date();
    const dateString = now.toISOString().replace(/[:.]/g, "-");

    XLSX.writeFile(
        workbook,
        `throughput_all_stations_${dateString}.xlsx`
    );

    setError("");
};
useEffect(() => {
    const handleExportEvent = () => {
        handleExportExcel();
    };

    window.addEventListener(
        "export-throughput-excel",
        handleExportEvent
    );

    return () => {
        window.removeEventListener(
            "export-throughput-excel",
            handleExportEvent
        );
    };
}, [handleExportExcel]);
    // Récupérer l'historique toutes les 2 secondes.
    useEffect(() => {
        let mounted = true;
        let inProgress = false;

        const fetchThroughput = async () => {
            if (inProgress) return;

            inProgress = true;

            try {
                const response = await fetch(API_URL, {
                    headers: {
                        Accept: "application/json",
                    },
                });

                if (!response.ok) {
                    throw new Error(`Erreur HTTP ${response.status}`);
                }

                const data = await response.json();

                const incoming = Array.isArray(data)
                    ? data
                    : data.measurements;

                if (!Array.isArray(incoming)) {
                    throw new Error(
                        "Format de données throughput invalide."
                    );
                }

                if (!mounted) return;

                setMeasurements((previous) => {
                    const merged = new Map();

                    // Conserver les mesures déjà reçues.
                    for (const item of previous) {
                        const key = [
                            item.timestamp,
                            item.mac,
                            item.interface,
                        ].join("_");

                        merged.set(key, item);
                    }

                    // Ajouter ou actualiser les mesures reçues.
                    for (const item of incoming) {
                        const key = [
                            item.timestamp,
                            item.mac,
                            item.interface,
                        ].join("_");

                        merged.set(key, item);
                    }

                    // Garder uniquement les 10 dernières minutes.
                    const cutoff = Date.now() / 1000 - 10 * 60;

                    return [...merged.values()]
                        .filter(
                            (item) =>
                                Number(item.timestamp) >= cutoff
                        )
                        .sort(
                            (a, b) =>
                                Number(a.timestamp) -
                                Number(b.timestamp)
                        )
                        .slice(-MAX_POINTS);
                });

                setError("");
                setLoading(false);
            } catch (err) {
                if (mounted) {
                    setError(
                        `Impossible de récupérer le throughput : ${err.message}`
                    );
                    setLoading(false);
                }

                console.error("Erreur API throughput :", err);
            } finally {
                inProgress = false;
            }
        };

        fetchThroughput();

        const interval = setInterval(fetchThroughput, 2000);

        return () => {
            mounted = false;
            clearInterval(interval);
        };
    }, []);

    // Liste des stations.
    const stations = useMemo(
        () =>
            [
                ...new Set(
                    measurements
                        .map((item) => item.mac)
                        .filter(Boolean)
                ),
            ].sort(),
        [measurements]
    );

    // Filtrer la station sélectionnée.
    const filteredMeasurements = useMemo(() => {
        if (selectedStation === "all") {
            return measurements;
        }

        return measurements.filter(
            (item) => item.mac === selectedStation
        );
    }, [measurements, selectedStation]);

    // Interfaces présentes dans l'historique.
    const interfaces = useMemo(
        () =>
            [
                ...new Set(
                    filteredMeasurements
                        .map((item) => item.interface)
                        .filter(Boolean)
                ),
            ].sort(),
        [filteredMeasurements]
    );

    // Préparer une courbe par station et par interface.
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

            const throughput = Number(item.throughput_mbps);

            if (
                !Number.isFinite(timestamp) ||
                Number.isNaN(date.getTime()) ||
                !item.mac ||
                !item.interface ||
                !Number.isFinite(throughput)
            ) {
                continue;
            }

            const timeKey = String(timestamp);

            if (!grouped.has(timeKey)) {
                grouped.set(timeKey, {
                    timestamp,
                    time: date.toLocaleTimeString("fr-FR", {
                        hour: "2-digit",
                        minute: "2-digit",
                    }),
                });
            }

            const lineKey = `${item.mac} | ${item.interface}`;

            grouped.get(timeKey)[lineKey] = throughput;

            keys.add(lineKey);
        }

        return {
            chartData: [...grouped.values()].sort(
                (a, b) => a.timestamp - b.timestamp
            ),
            lineKeys: [...keys].sort(),
        };
    }, [filteredMeasurements]);

    return (
        <Box
            height="100%"
            width="100%"
            display="flex"
            flexDirection="column"
            gap={2}
        >
            {/* Titre et filtre */}
            <Box
                display="flex"
                justifyContent="space-between"
                alignItems="center"
                flexWrap="wrap"
                gap={2}
            >
                <Box>
                    <Typography variant="h5">
                        Throughput Evolution Per Station
                    </Typography>

                    <Typography
                        variant="body2"
                        color="text.secondary"
                    >
                        Tri-Band Steering Monitoring
                    </Typography>
                </Box>

                <FormControl
                    size="small"
                    sx={{ minWidth: 260 }}
                >
                    <InputLabel id="throughput-station-label">
                       Wi-Fi Stations 
                    </InputLabel>

                    <Select
                        labelId="throughput-station-label"
                        value={selectedStation}
                        label="Wi-Fi Stations"
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

            {error && (
                <Alert severity="error">
                    {error}
                </Alert>
            )}

            {loading && (
                <Alert severity="info">
                    Connexion à l'API throughput...
                </Alert>
            )}

            {!loading &&
                !error &&
                measurements.length === 0 && (
                    <Alert severity="info">
                        En attente des premières mesures de débit...
                    </Alert>
                )}

            {/* Graphique */}
            <Box
                flex={1}
                minHeight={350}
                width="100%"
            >
                <ResponsiveContainer width="100%" height="100%">
                    <RechartsLineChart
                        data={chartData}
                        margin={{
                            top: 20,
                            right: 30,
                            left: 15,
                            bottom: 10,
                        }}
                    >
                        <CartesianGrid
                            strokeDasharray="3 3"
                            opacity={0.3}
                        />

                        <XAxis
                            dataKey="time"
                            minTickGap={30}
                            tick={{ fontSize: 11 }}
                        />

                        <YAxis
                            tick={{ fontSize: 12 }}
                            tickFormatter={(value) => `${value} Mbps`}
                            domain={[0, "auto"]}
                            width={75}
                        />

                        <Tooltip
                            formatter={(value) => [
                                `${Number(value).toFixed(2)} Mbps`,
                                "Throughput",
                            ]}
                        />

                        <Legend />

                        {lineKeys.map((key, index) => (
                            <Line
                                key={key}
                                type="monotone"
                                dataKey={key}
                                name={key}
                                connectNulls={false}
                                dot={false}
                                strokeWidth={2}
                                stroke={
                                    lineColors[
                                        index % lineColors.length
                                    ]
                                }
                                isAnimationActive={false}
                            />
                        ))}
                    </RechartsLineChart>
                </ResponsiveContainer>
            </Box>

            {/* Informations */}
            <Typography
                variant="caption"
                color="text.secondary"
            >
                {measurements.length} mesures ·{" "}
                {stations.length} station(s) ·{" "}
                {interfaces.length} interface(s) ·{" "}
                10 minutes Record
            </Typography>
        </Box>
    );
};

export default LineChartThroughput;
