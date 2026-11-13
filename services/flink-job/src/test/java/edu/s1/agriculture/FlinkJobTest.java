package edu.s1.agriculture;

import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

class FlinkJobTest {
    @Test void parsesContractReadingsAndIrrigation() {
        FlinkJob.Reading reading = FlinkJob.parseReading("{\"sensor_id\":\"s1\",\"farm_id\":\"f1\",\"plot_id\":\"p1\",\"moisture_pct\":20.0,\"temperature_c\":25.0,\"timestamp_ms\":60001}");
        assertNotNull(reading); assertEquals("f1", reading.farm_id); assertEquals(60001, reading.getTimestampMs());
        FlinkJob.Irrigation water = FlinkJob.parseIrrigation("{\"event_id\":\"e1\",\"farm_id\":\"f1\",\"plot_id\":\"p1\",\"crop\":\"tomato\",\"action\":\"WATER\",\"water_litres\":12.5,\"decided_at_ms\":61000}");
        assertNotNull(water); assertEquals(61000, water.getTimestampMs()); assertEquals(12.5, water.water_litres);
    }

    @Test void rejectsMalformedIncompleteAndInvalidTimestampRecords() {
        assertNull(FlinkJob.parseReading("not json"));
        assertNull(FlinkJob.parseReading("{\"sensor_id\":\"s1\",\"moisture_pct\":20}"));
        assertNull(FlinkJob.parseReading("{\"sensor_id\":\"s1\",\"farm_id\":\"f1\",\"moisture_pct\":20,\"temperature_c\":25,\"timestamp_ms\":0}"));
        assertNull(FlinkJob.parseIrrigation("{\"event_id\":\"e\",\"farm_id\":\" \",\"action\":\"WATER\",\"water_litres\":5,\"decided_at_ms\":9}"));
    }

    @Test void flinkEventTimeWindowsCombineOutOfOrderInputsAndAdvanceOnBoundedWatermarks() throws Exception {
        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.getConfig().setGlobalJobParameters(org.apache.flink.api.java.utils.ParameterTool.fromMap(java.util.Collections.singletonMap("test", "true")));
        org.apache.flink.configuration.Configuration config = new org.apache.flink.configuration.Configuration();
        config.setString("blob.server.port", "6124");
        env.configure(config, getClass().getClassLoader());
        env.setParallelism(1);
        // Input order is deliberately out of timestamp order. The final bounded-source watermark closes both windows.
        FlinkJob.Reading r1 = reading("s1", 30.0, 59_999), r2 = reading("s2", 10.0, 1_000),
                r4 = reading("s1", 20.0, 2_000), r3 = reading("s1", 20.0, 60_000);
        FlinkJob.Irrigation i1 = irrigation("e1", 15, 30_000), i2 = irrigation("e2", 7, 60_001);
        WatermarkStrategy<FlinkJob.Reading> rw = FlinkJob.watermarks((r, p) -> r.timestamp_ms);
        WatermarkStrategy<FlinkJob.Irrigation> iw = FlinkJob.watermarks((i, p) -> i.decided_at_ms);
        List<FlinkJob.Summary> actual = new java.util.ArrayList<>();
        try (org.apache.flink.util.CloseableIterator<FlinkJob.Summary> output = FlinkJob.combine(
                env.fromCollection(Arrays.asList(r1, r2, r4, r3)).assignTimestampsAndWatermarks(rw),
                env.fromCollection(Arrays.asList(i1, i2)).assignTimestampsAndWatermarks(iw)).executeAndCollect()) {
            while (output.hasNext()) actual.add(output.next());
        }
        List<FlinkJob.Summary> f1 = actual.stream().filter(s -> s.farm_id.equals("f1")).collect(Collectors.toList());
        assertEquals(2, f1.size());
        FlinkJob.Summary first = f1.stream().filter(s -> s.window_start_ms == 0).findFirst().orElseThrow();
        assertEquals(3, first.readings); assertEquals(2, first.sensors); assertEquals(20.0, first.avg_moisture_pct, 0.001);
        assertEquals(10.0, first.min_moisture_pct, 0.001); assertEquals(30.0, first.max_moisture_pct, 0.001);
        assertEquals(1, first.watering_events); assertEquals(15.0, first.water_litres, 0.001); assertEquals(60_000, first.window_end_ms);
        FlinkJob.Summary second = f1.stream().filter(s -> s.window_start_ms == 60_000).findFirst().orElseThrow();
        assertEquals(1, second.readings); assertEquals(1, second.sensors); assertEquals(1, second.watering_events); assertEquals(7, second.water_litres, 0.001);
        assertEquals(10_000, FlinkJob.OUT_OF_ORDER_MS);
        assertEquals(60_000, FlinkJob.WINDOW_MS);
    }

    private static FlinkJob.Reading reading(String sensor, double moisture, long ts) { FlinkJob.Reading r=new FlinkJob.Reading();r.sensor_id=sensor;r.farm_id="f1";r.moisture_pct=moisture;r.temperature_c=20;r.timestamp_ms=ts;return r; }
    private static FlinkJob.Irrigation irrigation(String id, double litres, long ts) { FlinkJob.Irrigation i=new FlinkJob.Irrigation();i.event_id=id;i.farm_id="f1";i.action="WATER";i.water_litres=litres;i.decided_at_ms=ts;return i; }
}
