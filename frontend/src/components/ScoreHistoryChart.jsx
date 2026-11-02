import React, { useMemo } from "react";
import { Box, Card, CardContent, Typography } from "@mui/material";
import {
    ResponsiveContainer,
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
} from "recharts";

const COLORS = [
    "#4cceac",
    "#6870fa",
    "#db4f4a",
    "#ff9800",
    "#00bcd4",
    "#ab47bc",
    "#8bc34a",
    "#f06292",
    "#795548",
    "#607d8b",
    "#cddc39",
    "#e91e63",
];

function getDeviceId(device, index = 0) {
    return String(
        device?._scoreId ||
            device?.mac ||
            device?.hostname ||
            `device_${index}`
    );
}

function getScoreKey(deviceId) {
    return `score_${encodeURIComponent(String(deviceId))}`;
}

function formatTime(timestamp) {
    if (timestamp === null || timestamp === undefined || timestamp === "") {
        return "—";
    }

    const date = new Date(Number(timestamp));
    if (Number.isNaN(date.getTime())) return "—";

    return date.toLocaleTimeString("fr-FR", {
        hour: "2-digit",
        minute: "2-digit"
    });
}

function getDeviceLabel(device, index) {
    const id = getDeviceId(device, index);
    if (device?.hostname && device?.mac) {
        return `${device.hostname} (${device.mac})`;
    }
    return device?.hostname || device?.mac || id;
}

export default function ScoreHistoryChart({ history = [], devices = [] }) {
    const validHistory = Array.isArray(history) ? history : [];
    const validDevices = Array.isArray(devices) ? devices : [];

    const series = useMemo(
        () =>
            validDevices.map((device, index) => {
                const id = getDeviceId(device, index);
                return {
                    key: getScoreKey(id),
                    label: getDeviceLabel(device, index),
                };
            }),
        [validDevices]
    );

    const hasScores = validHistory.some((point) =>
        series.some(({ key }) => {
            const value = point?.[key];
            return (
                value !== null &&
                value !== undefined &&
                value !== "" &&
                Number.isFinite(Number(value))
            );
        })
    );

    let message = "";
    if (validDevices.length === 0) {
        message = "Aucun appareil reçu depuis le backend.";
    } else if (validHistory.length === 0) {
        message = "En attente des premières mesures...";
    } else if (!hasScores) {
        message =
            "Aucun score numérique disponible. Vérifie les champs scores et current_band renvoyés par l'API.";
    }

    return (
        <Card sx={{ minHeight: 430 }}>
            <CardContent
                sx={{
                    minHeight: 430,
                    display: "flex",
                    flexDirection: "column",
                    boxSizing: "border-box",
                }}
            >
            
                <Typography variant="body2" color="text.secondary" mb={3}>
             Each curve represents the device's score on its current Wi-Fi band. Missing values ​​are not interpolated.
                </Typography>

                {message ? (
                    <Box
                        display="flex"
                        alignItems="center"
                        justifyContent="center"
                        flex={1}
                        minHeight={280}
                        px={2}
                    >
                        <Typography color="text.secondary" textAlign="center">
                            {message}
                        </Typography>
                    </Box>
                ) : (
                    <Box sx={{ width: "100%", flex: 1, minHeight: 320 }}>
                        <ResponsiveContainer width="100%" height={350}>
                            <LineChart
                                data={validHistory}
                                margin={{
                                    top: 10,
                                    right: 24,
                                    left: 8,
                                    bottom: 12,
                                }}
                            >
                                <CartesianGrid
                                    strokeDasharray="3 3"
                                    opacity={0.25}
                                />

                                <XAxis
                                    dataKey="timestamp"
                                    type="number"
                                    domain={["dataMin", "dataMax"]}
                                    tickFormatter={formatTime}
                                    tickCount={7}
                                    minTickGap={30}
                                />

                                <YAxis
                                    domain={[0, 100]}
                                    allowDataOverflow
                                    label={{
                                        value: "Score",
                                        angle: -90,
                                        position: "insideLeft",
                                    }}
                                />

                                <Tooltip
                                    labelFormatter={(value) =>
                                        `Heure : ${formatTime(value)}`
                                    }
                                    formatter={(value, name) => {
                                        const numeric = Number(value);
                                        return [
                                            value === null ||
                                            value === undefined ||
                                            value === "" ||
                                            !Number.isFinite(numeric)
                                                ? "Pas de mesure"
                                                : numeric.toFixed(2),
                                            name,
                                        ];
                                    }}
                                />

                                <Legend />

                                {series.map((device, index) => (
                                    <Line
                                        key={device.key}
                                        type="monotone"
                                        dataKey={device.key}
                                        name={device.label}
                                        stroke={COLORS[index % COLORS.length]}
                                        strokeWidth={2}
                                        dot={false}
                                        connectNulls={false}
                                        isAnimationActive={false}
                                    />
                                ))}
                            </LineChart>
                        </ResponsiveContainer>
                    </Box>
                )}

                <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ mt: 1 }}
                >
                    {validHistory.length} / 300 conserved mesures · {validDevices.length} known device(s)
                </Typography>
            </CardContent>
        </Card>
    );
}
