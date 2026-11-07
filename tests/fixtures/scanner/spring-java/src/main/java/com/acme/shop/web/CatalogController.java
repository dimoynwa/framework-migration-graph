package com.acme.shop.web;

import com.acme.shop.service.CatalogService;
import com.acme.shop.service.Widget;
import com.acme.shop.service.CatalogService.Page;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * Own-package imports (``com.acme.shop.service.*``) are the repo's own code and
 * must not become facts; the Spring ones must. ``Page`` is a nested type of an
 * own class, imported with its dots.
 */
@RestController
@RequestMapping(value = "/widgets", method = RequestMethod.GET)
public class CatalogController {

    private final CatalogService service;
    private final Page firstPage;
    private List<Widget> cached;

    public CatalogController(CatalogService service, Page firstPage) {
        this.service = service;
        this.firstPage = firstPage;
    }

    @GetMapping("/{id}")
    public ResponseEntity<Widget> one(@PathVariable("id") String id) {
        Widget widget = service.find(id);
        return ResponseEntity.status(HttpStatus.OK).body(widget);
    }

    /** A call on a local variable: not resolved (spec1 Non-Goals). */
    public String label(Widget widget) {
        return widget.name();
    }
}
