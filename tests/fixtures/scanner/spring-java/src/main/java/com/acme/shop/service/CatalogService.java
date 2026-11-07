package com.acme.shop.service;

import java.util.ArrayList;
import java.util.List;

public class CatalogService {

    public record Page(int number, int size) {}

    public Widget find(String id) {
        return new Widget(id);
    }

    public List<Widget> all() {
        return new ArrayList<>();
    }
}
