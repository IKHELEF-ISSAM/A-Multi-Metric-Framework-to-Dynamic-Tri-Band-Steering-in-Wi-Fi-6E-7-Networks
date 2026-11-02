
import { useEffect, useMemo, useState } from "react";

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
    Button,
} from "@mui/material";

import FileDownloadIcon from "@mui/icons-material/FileDownload";
import * as XLSX from "xlsx";

const API_URL = "/api/rssi";
const MAX_POINTS = 5000;

// Couleurs des courbes RSSI
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

const LineChart = () => {
    const [measurements, setMeasurements] = useState([]);
    const [selectedStation, setSelectedStation] = useState("all");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(true);

    // =====================================================
    // EXPORT EXCEL
    // =====================================================

    const exportToExcel = () => {
        if (measurements.length === 0) {
            alert("Aucune mesure RSSI à exporter.");
            return;
        }

        const excelData = measurements.map((item) => {
            const timestamp = Number(item.timestamp);

            const milliseconds =
                timestamp < 1e12
                    ? timestamp * 1000
                    : timestamp;

            const date = new Date(milliseconds);

            return {
                "Date et heure":
                    Number.isFinite(timestamp) &&
                    !Number.isNaN(date.getTime())
                        ? date.toLocaleString("fr-FR")
                        : "",
                "Station MAC": item.mac ?? "",
                "Interface Wi-Fi": item.interface ?? "",
                "RSSI (dBm)": item.rssi ?? "",
            };
        });

        const worksheet = XLSX.utils.json_to_sheet(excelData);

        // Ajustement de la largeur des colonnes
        worksheet["!cols"] = [
            { wch: 22 },
            { wch: 22 },
            { wch: 20 },
            { wch: 15 },
        ];

        const workbook = XLSX.utils.book_new();

        XLSX.utils.book_append_sheet(
            workbook,
            worksheet,
            "Mesures RSSI"
        );

        // Nom du fichier avec la date et l'heure
        const now = new Date();

        const dateSuffix = [
            now.getFullYear(),
            String(now.getMonth() + 1).padStart(2, "0"),
            String(now.getDate()).padStart(2, "0"),
        ].join("-");

        const timeSuffix = [
            String(now.getHours()).padStart(2, "0"),
            String(now.getMinutes()).padStart(2, "0"),
            String(now.getSeconds()).padStart(2, "0"),
        ].join("-");

        const filename =
            `mesures_RSSI_${dateSuffix}_${timeSuffix}.xlsx`;

        XLSX.writeFile(workbook, filename);
    };

    // =====================================================
    // RÉCUPÉRATION PÉRIODIQUE DES MESURES RSSI
    // =====================================================

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
                    const text = await response.text();

                    throw new Error(
                        `Réponse non JSON : ${text.slice(0, 150)}`
                    );
                }

                const data = await response.json();

                const incoming = Array.isArray(data)
                    ? data
                    : data.measurements;

                if (!Array.isArray(incoming)) {
                    throw new Error(
                        "L'API doit renvoyer un tableau measurements."
                    );
                }

                if (mounted) {
                    setMeasurements((previous) => {
                        const merged = new Map();

                        // Conserver les mesures déjà reçues
                        for (const item of previous) {
                            const key = [
                                item.timestamp,
                                item.mac,
                                item.interface,
                            ].join("_");

                            merged.set(key, item);
                        }

                        // Ajouter ou actualiser les mesures reçues
                        for (const item of incoming) {
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

    // =====================================================
    // LISTE DES STATIONS DÉTECTÉES
    // =====================================================

    const stations = useMemo(() => {
        return [
            ...new Set(
                measurements
                    .map((item) => item.mac)
                    .filter(Boolean)
            ),
        ].sort();
    }, [measurements]);

    // =====================================================
    // FILTRAGE PAR STATION
    // =====================================================

    const filteredMeasurements = useMemo(() => {
        if (selectedStation === "all") {
            return measurements;
        }

        return measurements.filter(
            (item) => item.mac === selectedStation
        );
    }, [measurements, selectedStation]);

    // =====================================================
    // LISTE DES INTERFACES
    // =====================================================

    const interfaces = useMemo(() => {
        return [
            ...new Set(
                filteredMeasurements
                    .map((item) => item.interface)
                    .filter(Boolean)
            ),
        ].sort();
    }, [filteredMeasurements]);

    // =====================================================
    // PRÉPARATION DES DONNÉES DU GRAPHIQUE
    // =====================================================

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

            const point = grouped.get(timeKey);

            const lineKey = `${item.mac} | ${item.interface}`;

            const rssi = Number(item.rssi);

            point[lineKey] = Number.isFinite(rssi)
                ? rssi
                : null;

            keys.add(lineKey);
        }

        return {
            chartData: [...grouped.values()].sort(
                (a, b) => a.timestamp - b.timestamp
            ),
            lineKeys: [...keys].sort(),
        };
    }, [filteredMeasurements]);

    // =====================================================
    // INTERFACE UTILISATEUR
    // =====================================================

    return (
        <Box
            height="100%"
            width="100%"
            display="flex"
            flexDirection="column"
            gap={2}
        >
            {/* EN-TÊTE ET FILTRE */}

            <Box
                display="flex"
                justifyContent="space-between"
                alignItems="center"
                flexWrap="wrap"
                gap={2}
            >
                <Box>
                    <Typography variant="h5">
                        RSSI Evolution Per Station
                    </Typography>

                    <Typography
                        variant="body2"
                        color="text.secondary"
                    >
                        Tri-Bands Steering Monitoring
                    </Typography>
                </Box>

                <Box
                    display="flex"
                    alignItems="center"
                    flexWrap="wrap"
                    gap={2}
                >
                    {/* FILTRE DES STATIONS */}

                    <FormControl
                        size="small"
                        sx={{ minWidth: 260 }}
                    >
                        <InputLabel id="station-select-label">
                            Wi-Fi Stations
                        </InputLabel>

                        <Select
                            labelId="station-select-label"
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
                                <MenuItem
                                    key={mac}
                                    value={mac}
                                >
                                    {mac}
                                </MenuItem>
                            ))}
                        </Select>
                    </FormControl>

                    {/* BOUTON EXPORT EXCEL */}

                    <Button
                        variant="contained"
                        color="success"
                        startIcon={<FileDownloadIcon />}
                        onClick={exportToExcel}
                        disabled={measurements.length === 0}
                    >
                        Export to Excel
                    </Button>
                </Box>
            </Box>

            {/* MESSAGES D'ÉTAT */}

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
                measurements.length === 0 && (
                    <Alert severity="info">
                        Waiting for RSSI first mesures...
                    </Alert>
                )}

            {/* GRAPHIQUE RSSI */}

            <Box
                flex={1}
                minHeight={350}
                width="100%"
            >
                <ResponsiveContainer
                    width="100%"
                    height="100%"
                >
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

                        <Tooltip />

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

            {/* STATISTIQUES */}

            <Typography
                variant="caption"
                color="text.secondary"
            >
                {measurements.length} mesures in memory ·{" "}
                {stations.length} station(s) ·{" "}
                {interfaces.length} interface(s)
            </Typography>
        </Box>
    );
};

export default LineChart;

