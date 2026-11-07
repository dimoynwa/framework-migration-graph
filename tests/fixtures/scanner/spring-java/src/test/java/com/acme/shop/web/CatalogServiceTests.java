package com.acme.shop.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import com.acme.shop.service.CatalogService;
import com.acme.shop.service.Widget;

/**
 * A test source: every fact lands with ``test: true`` (AC-5.3), and the static
 * imports become members of the class they came from.
 */
@SpringBootTest
public class CatalogServiceTests {

    @Autowired
    private CatalogService service;

    @Mock
    private Widget widget;

    @Test
    public void findsWidgets() {
        when(service.find("a")).thenReturn(widget);
        verify(service).find("a");
        assertThat(service.all()).isEmpty();
    }
}
