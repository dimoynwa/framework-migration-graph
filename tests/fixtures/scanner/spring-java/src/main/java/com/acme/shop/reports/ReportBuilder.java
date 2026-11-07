package com.acme.shop.reports;

import org.springframework.stereotype.Component;
import java.util.ArrayList;
import java.util.*;
import static java.util.Collections.*;

/**
 * Two wildcard imports, so AC-5.2 has something to check:
 *
 * - ``java.util.*`` must supply ``Map`` and ``Arrays`` (both used below) and
 *   must not supply ``Report`` (declared here), ``ArrayList`` (imported
 *   explicitly, so the explicit import explains it) or ``String`` (a
 *   ``java.lang`` type that needs no import at all).
 * - ``Collections.*`` is the static form: the bare ``sort`` / ``emptyList``
 *   calls are members of ``java.util.Collections``.
 *
 * The class also uses a fully qualified name with no import
 * (``org.springframework.util.Assert``), which spec6's groupIds make external.
 */
@Component
public class ReportBuilder {

    private final Map<String, Integer> counts = new HashMap<>();

    public List<String> build() {
        List<String> names = new ArrayList<>(counts.keySet());
        sort(names);
        String[] fixed = {"a", "b"};
        int size = Arrays.stream(fixed).toList().size();
        org.springframework.util.Assert.isTrue(size > 0, "empty");
        Report report = new Report(size);
        return emptyList();
    }

    /** Declared here, so no wildcard import supplies it. */
    public record Report(int size) {}
}
