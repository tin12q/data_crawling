        $(document).ready(function () {

            function Base64ToBytes(base64) {
                var s = window.atob(base64);
                var bytes = new Uint8Array(s.length);
                for (var i = 0; i < s.length; i++) {
                    bytes[i] = s.charCodeAt(i);
                }
                return bytes;
            };

            $('body').on("keyup", '#searchValue', function (e) {
                if (e.keyCode === 13)
                    addToQueryBox($("#btnAdd"));
            });

            // We don't want them adding a new line in the query box so just fire the advanced search when enter key is pressed
            $('body').on("keydown", '#queryBox', function (e) {
                if (e.keyCode === 13) {
                    e.preventDefault();
                    e.stopPropagation();
                    if ($("#queryBox").val() != '')
                        $("#btnAdvancedSearch").click();
                }
            });

            // Fire the search button click when enter is pressed in simple search
            // enable/disable the search butttons according to whether any data entered for advanced or simple search
            $('body').on("keyup", '#searchCriteria, #queryBox', function (e) {
                if (e.keyCode === 13) {
                    if ($(this).attr('id') == "queryBox") {
                        if ($("#queryBox").val() != '')
                            $("#btnAdvancedSearch").click();
                    }
                    else if ($("#searchCriteria").val() != '')
                        $("#btnSearchSimple").click();
                }

                if ($(this).val() != '')
                    $(".btnSearch").removeClass('disabled');
                else
                    $(".btnSearch").addClass('disabled');
            });

            // We need to determine if we are on the main search page or the details page.  If on the main search page, then we can just do an
            // ajax call returning the partial view with the search results.  If we are on the details page, then we need to do a form submit
            // to do a round trip and return back to the index page with the results for the search entered into whichever search we are performing
            // Advanced or Simple.
            $('body').on("click", '.btnSearch', function () {
                if ($("#searchCriteria").val() === '' && $("#queryBox").val() === '') {
                    $("#errorMessages").html("Please enter a query before attempting to search.")
                    $("#errorMessages").removeClass('d-none');
                    return;
                }

                var model = createModel(1);

                // What page are we on?
                var currentUrl = $(location).attr('href');
                if (currentUrl.indexOf('Details') > 0) {
                    // We need to redirect to the Search controller Index method with the search type and search criteria
                    url = "/NSLSL/Search/Index?searchType=" + ($("#advancedSearchDisplay").is(':visible') ? 'advanced' : 'simple') + "&searchCriteria=" + model.SearchCriteria;
                    window.location = url;
                    return;
                }

                // We're on the main search page so do the ajax call to get the results
                // Turn on spinner icon on the search button(s)
                $(".search-spinner").removeClass("d-none");
                $(".searchicon").addClass("d-none");

                var token = $('input[name="__RequestVerificationToken"]', $('#__AjaxAntiForgeryForm')).val();
                var tmpSelectedPubCheckboxes = selectedPubIds;

                $.ajax({
                    url: "/NSLSL/Search/SearchAjax",
                    cache: false,
                    type: "POST",
                    data: { __RequestVerificationToken: token, model: model },
                    contentType: 'application/x-www-form-urlencoded; charset=utf-8',
                    success: function (data) {
                        if (data.result == 'Redirect')
                            window.location = data.url;
                        else {
                            $('#searchResults').html(data);

                            // Set the text for the selected results dropdown options for emailing/saving
                            if ($(".reset-icon").hasClass('d-none')) {
                                // We are here due to the reset filters button being clicked, so recheck any previously checked pubs
                                selectedPubIds = tmpSelectedPubCheckboxes;
                                setSelectedPubCheckboxes();
                            } else {
                                $(".selectionOptions option[value='selected']").text("Selected Results (0)");
                                selectedPubIds = [];
                            }
                        }
                    },
                    error: function (jqXHR, textStatus, errorThrown) {
                        $("#loadingMessage").hide();
                        alert(jqXHR.responseText);
                    },
                    beforeSend: function (jqXHR, settings) {
                        $("#loadingMessage").show();
                    },
                    complete: function (jqXHR, settings) {
                        $("#loadingMessage").hide();
                        var element = document.getElementById("searchResultsSection")
                        if (element.classList.contains("col-12")) {
                            $("#searchResultsSection").addClass('card col-lg-9 col-md-12');
                        }
                        $('#searchFilterSection').show();
                        $('#searchResultList').show();
                        $('#searchResultsSection').show();
                        $('#searchResultDetail').hide();
                        $(".optionsSection").removeClass('d-none');

                        $(".search-spinner").addClass("d-none");
                        $(".searchicon").removeClass("d-none");
                        $(".reset-spinner").addClass("d-none");
                        $(".reset-icon").removeClass("d-none");
                    }
                })
            });

            $('#searchAdvance').on("click", function () {
                // Hide all the search results divs if switching between search types.
                $('#searchFilterSection').hide();
                $('#searchResultList').hide();
                $('#searchResultsSection').hide();
                $('#searchResultDetail').hide();
                $('.optionsSection').addClass('d-none');
                $("#navigationRefresh").hide();
                $("#returnToResults").hide();

                if ($("#advancedSearchDisplay").is(':visible')) {
                    // We are going from the advanced search to the simple search
                    $("#searchCriteria").val($("#queryBox").val());
                    $("#advancedSearchDisplay").hide();
                    $("#simpleSearchDisplay").show();
                    $("#searchAdvance").text("Advanced Search");

                    if ($("#searchCriteria").val() != '')
                        $(".btnSearch").removeClass('disabled');
                    else
                        $(".btnSearch").addClass('disabled');
                }
                else {
                    if (typeof $(".advancedSearchContainer").html() === 'undefined') {
                        $.ajax({
                            url: "/NSLSL/Search/AdvancedSearchAjax",
                            cache: true,
                            type: "GET",
                            success: function (data) {
                                $('#advancedSearchDisplay').html(data);
                                $('.optionsSection').addClass('d-none');
                            },
                            error: function (jqXHR, textStatus, errorThrown) {
                                $("#loadingMessage").hide();
                                alert(jqXHR.responseText);
                            },
                            beforeSend: function (jqXHR, settings) {
                                $("#loadingMessage").show();
                            },
                            complete: function (jqXHR, settings) {
                                // Did we get here from the Details page?  If so then set the queryBox value and click the search button
                                if ($("#SearchType").val() != undefined && $("#SearchType").val() != '') {
                                    // Clear out our SearchType so that the queryBox won't be set to the SearchCriteria value if the advanced link is cicked again
                                    $("#SearchType").val('');
                                    $("#queryBox").val(searchCriteria);
                                    $("#btnAdvancedSearch").click()
                                }

                                $("#queryBox").val($("#searchCriteria").val());
                                if ($("#queryBox").val() != '')
                                    $(".btnSearch").removeClass('disabled');
                                else
                                    $(".btnSearch").addClass('disabled');
                                $("#loadingMessage").hide();
                            }
                        });
                    }
                    else {
                        // The advanced search div was previously loaded so just replace the querybox value with our simple search value
                        $("#queryBox").val($("#searchCriteria").val());
                        if ($("#queryBox").val() != '')
                            $(".btnSearch").removeClass('disabled');
                        else
                            $(".btnSearch").addClass('disabled');
                    }
                    $('#advancedSearchDisplay').show();
                    $("#simpleSearchDisplay").hide();
                    $("#searchAdvance").text("Simple Search");
                }
            });

            /*
             * Show hide text box or from-to-fields div depending on field chosen in the dropdown.
             */
            $('body').on("change", '#searchOptions', function () {
                var fieldType = $("#searchOptions").find(':selected').data("columntype");
                if (fieldType === "int" && $("#fromToValues").hasClass('d-none')) {
                    $("#fromToValues").removeClass('d-none');
                    $("#searchValue").addClass('d-none');
                } else if (fieldType === "string" && $("#searchValue").hasClass('d-none')) {
                    $("#fromToValues").addClass('d-none');
                    $("#searchValue").removeClass('d-none');
                }
            });

            /*
             *One method for the three advanced search buttons.  Each has a data-operator field which determines the actual action.
             */
            $('body').on("click", '.btnAdd, #btnAdd', function () {
                addToQueryBox($(this));
            });

            $('body').on("click", '.btnClear', function () {
                $("#searchCriteria").val('');
                $("#queryBox").val('');
                $("#searchValue").val('');
                $("#btnAdd").text("ADD");
                $("#btnNot").addClass('d-none');
                $("#btnOr").addClass('d-none');
                $("#searchErrors").addClass('d-none');
                $(".btnSearch").addClass('disabled');
                $("#emptySearchTerm").html("");

            });

            // Ajax call when pagination buttons are clicked or a number entered in pagenumber field
            $('body').on("keyup click", '.pageNumber, .fetchpage', function (e) {
                if (e.keyCode === 13 || $(this).hasClass("fetchpage")) {
                    var obj = $(this);
                    if ($(this).hasClass("fetchpage")) {
                        if ($(this).attr("href") != '#') {
                            return;
                        }
                        var fetchPageNumber = $(this).data("val");
                        $(".pageNumber").val(fetchPageNumber);
                    }
                    else {
                        var fetchPageNumber = parseInt($(this).val());
                        if (fetchPageNumber > parseInt($("#NumPages").val()) || fetchPageNumber < 1) {
                            $(this).val($("#CurrentPage").val());
                            return;
                        }
                    }
                    $(this).addClass('d-none');
                    $(this).next().removeClass('d-none');

                    var model = createModel(fetchPageNumber);

                    var token = $('input[name="__RequestVerificationToken"]', $('#__AjaxAntiForgeryForm')).val();
                    $.ajax({
                        url: "/NSLSL/Search/FetchPageAjax",
                        cache: false,
                        type: "POST",
                        data: { __RequestVerificationToken: token, model: model },
                        contentType: 'application/x-www-form-urlencoded; charset=utf-8',
                        success: function (data) {
                            $('#searchResults').html(data);
                        },
                        error: function (jqXHR, textStatus, errorThrown) {
                            $("#loadingMessage").hide();
                            alert(jqXHR.responseText);
                        },
                        beforeSend: function (jqXHR, settings) {
                            $("#loadingMessage").show();
                        },
                        complete: function (jqXHR, settings) {
                            // If we are paging from the bottom then scroll to the bottom of the page after fetching page
                            if (obj.parent().parent().parent().parent().parent().hasClass("isBottom")) {
                                window.scrollTo(0, document.body.scrollHeight);
                            }
                            setSelectedPubCheckboxes();
                        }
                    })
                }

                return false;
            });

            // Ajax call when change options "Set" button is clicked
            $('body').on("click", '#changeOptions', function (e) {
                if (($("#advancedSearchDisplay").is(':visible'))) {
                    var searchCriteria = $("#queryBox").val();
                } else {
                    var searchCriteria = $("#searchCriteria").val();
                }

                var model = {
                    PageFormat: $("#OptionFormat option:selected").val(),
                    CurrentPage: $(".pageNumber").val(),
                    SortBy: $("#OptionSortBy option:selected").val(),
                    SortAscending: $("#OptionSortAscending").hasClass("fa fa-sort-amount-down-alt"),
                    SearchCriteria: searchCriteria,
                    NumberPerPage: $("#OptionNumPerPage option:selected").val(),
                    DefaultFilterCriteria: $("#DefaultFilterCriteria").val()
                };

                var form = $('#__AjaxAntiForgeryForm');
                var token = $('input[name="__RequestVerificationToken"]', form).val();
                $.ajax({
                    url: "/NSLSL/Search/ChangeDisplayOptionsAjax",
                    cache: false,
                    type: "POST",
                    data: { __RequestVerificationToken: token, model: model },
                    contentType: 'application/x-www-form-urlencoded; charset=utf-8',
                    success: function (data) {
                        $('#searchResults').html(data);
                    },
                    error: function (jqXHR, textStatus, errorThrown) {
                        $("#loadingMessage").hide();
                        alert(jqXHR.responseText);
                    },
                    beforeSend: function (jqXHR, settings) {
                        $("#loadingMessage").show();
                    },
                    complete: function (jqXHR, settings) {
                        // Set the text for the selected results dropdown options for emailing/saving
                        $(".selectionOptions option[value='selected']").text("Selected Results (0)");
                        selectedPubIds = [];
                        $(".options-spinner").addClass("d-none");
                    }
                })
            });

            $('body').on("change", '#OptionsSortByInline', function () {
                $("#OptionSortBy").val($("#OptionsSortByInline option:selected").val());
                $(".pageNumber").val(1);
                $("#changeOptions").click();
                // Show the spinner
                $(this).next().removeClass("d-none");
            });

            $('body').on("change", '#OptionsNumPerPageInline', function () {
                $("#OptionNumPerPage").val($("#OptionsNumPerPageInline option:selected").val());
                $(".pageNumber").val(1);
                $("#changeOptions").click();
                $(this).next().removeClass("d-none");
            });

            $('body').on("change", '#OptionFormatInline', function () {
                $("#OptionFormat").val($("#OptionFormatInline option:selected").val());
                $("#changeOptions").click();
                $(this).next().removeClass("d-none");
            });

            // Change ascending/descending display icon when direction changed in options modal
            $('.btn-sortdirection').on("click", function () {
                changeSortIcon($("#OptionSortAscending"));
                changeSortIcon($("#OptionSortAscendingInline"));
                if ($(this).hasClass('btn-sortdirection-inline')) {
                    $("#changeOptions").click();
                    $(this).next().removeClass("d-none");
                }
            });

            $('body').on("click", ".defaultFilter", function (e) {
                // Check the custom range years per customer request to show error if the to is less than the from.
                var fromYear = Number($("#fromPubYear").val());
                var toYear = Number($("#toPubYear").val());
                if (fromYear > toYear) {
                    toastr.error("From year must be less than to year");
                    return;
                } else if ((fromYear > 0 && fromYear.toString().length != 4) || (toYear > 0 && toYear.toString().length != 4)) {
                    toastr.error("Custom year range values must be 4 digits");
                    return;
                }

                var token = $('input[name="__RequestVerificationToken"]', $('#__AjaxAntiForgeryForm')).val();
                var filterOption = $(this).children().first();
                if (filterOption.length == 0) {
                    filterOption = $(this).prev();
                }
                filterOption.removeClass("d-none");
                buildDefaultFilterCriteria();
                var model = createModel(1);
                $.ajax({
                    url: "/NSLSL/Search/SearchAjax",
                    cache: false,
                    type: "POST",
                    data: { __RequestVerificationToken: token, model: model },
                    contentType: 'application/x-www-form-urlencoded; charset=utf-8',
                    success: function (data) {
                         $('#searchResults').html(data);
                    },
                    error: function (jqXHR, textStatus, errorThrown) {
                        $("#loadingMessage").hide();
                        alert(jqXHR.responseText);
                    },
                    beforeSend: function (jqXHR, settings) {
                        $("#loadingMessage").show();
                    },
                    complete: function (jqXHR, settings) {
                        $("#loadingMessage").hide();
                        filterOption.addClass("d-none");

                        // We want to restore any filter options that were checked before applying a filter
                        setSelectedPubCheckboxes();
                    }
                })
            });

            $('body').on("click", "#setAdditionalFilters", function (e) {
                // Loop through all our additional filter checkboxes showing/hiding as necessary in the DefaultFilters section
                var lastaddFilterGroup = '';
                var showaddFilterGroup = false;
                $(".additionalFilter").each(function (index) {
                    var currentaddFilterGroup = $(this).data("addfiltertype");
                    if (lastaddFilterGroup == '' || lastaddFilterGroup != currentaddFilterGroup) {
                        if (lastaddFilterGroup != '') {
                            if (showaddFilterGroup) {
                                $("#" + lastaddFilterGroup + "div").removeClass('d-none');
                            }
                            else {
                                $("#" + lastaddFilterGroup + "div").addClass('d-none');
                            }
                        }

                        showaddFilterGroup = false;
                        lastaddFilterGroup = currentaddFilterGroup;
                    }

                    // Need to determine if the checkbox type's div needs to be visible (if any of it's checkboxes are checked)
                    var filterToShowHide = $(this).data("addfilterid");
                    if (this.checked) {
                        // Show the checkbox in the filters side div
                        showaddFilterGroup = true;
                        $("#" + filterToShowHide).removeClass("d-none");
                    } else {
                        // Hide the checkbox in the filters side div and if checked, trigger the click to fire the ajax search to
                        // remove the filter from the results
                        $("#" + filterToShowHide).addClass("d-none");
                        if ($("#" + filterToShowHide).children("input").prop("checked") == true) {
                            $("#" + filterToShowHide).children("input").click();
                        }
                    }
                });

                //  Need to show/hide the final div after all the checkboxes have been processed in the each loop
                if (showaddFilterGroup) {
                    $("#" + lastaddFilterGroup + "div").removeClass('d-none');
                }
                else {
                    $("#" + lastaddFilterGroup + "div").addClass('d-none');
                }
            });

            $("#submitEmail").on("click", function () {
                // Check to make sure that not more than 10K records are selected

                $("#emailToError").addClass("d-none");
                $("#emailSelectError").addClass("d-none");
                $("#emailMaxMsg").removeClass("text-danger");

                var model = createModelForExport($("#CurrentPage").val(), "email");
                if (model == null)
                    return;

                // Check for valid email address entered.
                var regexForEmail = /^(([^<>()[\]\\.,;:\s@\"]+(\.[^<>()[\]\\.,;:\s@\"]+)*)|(\".+\"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
                if (!regexForEmail.test($("#emailTo").val())){
                    $("#emailToError").removeClass("d-none");
                    return;
                }

                // Check at least one result selected if the 'selected' option is chosen
                if (model.ExportOptions.Selection == 'selected' && model.ExportOptions.SelectedItems.length == 0) {
                    $("#emailSelectError").removeClass("d-none");
                    return;
                }

                $('#emailModal').modal('hide');

                var form = $('#__AjaxAntiForgeryForm');
                var token = $('input[name="__RequestVerificationToken"]', form).val();
                $.ajax({
                    url: "/NSLSL/Search/EmailSearchResults",
                    cache: false,
                    type: "POST",
                    data: { __RequestVerificationToken: token, model: model },
                    contentType: 'application/x-www-form-urlencoded; charset=utf-8',
                    success: function (data) {
                        if (data)
                            toastr.success("Email was successfully sent");
                        else
                            toastr.error("Email was not sent");
                    },
                    error: function (jqXHR, textStatus, errorThrown) {
                        toastr.error(jqXHR.responseText);
                    },
                    beforeSend: function (jqXHR, settings) {
                        $("#email-icon").removeClass("fa-envelope");
                        $("#email-icon").addClass("spinner spinner-border spinner-border-sm");
                    },
                    complete: function (jqXHR, settings) {
                        $("#email-icon").addClass("fa-envelope");
                        $("#email-icon").removeClass("spinner spinner-border spinner-border-sm");
                    }
                })
            });

            $("#submitSave").on("click", function () {
                $("#saveMaxMsg").removeClass("text-danger");
                $("#saveSelectError").addClass("d-none");

                var model = createModelForExport($("#CurrentPage").val(), "save");
                if (model == null)
                    return;

                // Check at least one result selected if the 'selected' option is chosen
                if (model.ExportOptions.Selection == 'selected' && model.ExportOptions.SelectedItems.length == 0) {
                    $("#saveSelectError").removeClass("d-none");
                    return;
                }

                $('#saveModal').modal('hide');

                var form = $('#__AjaxAntiForgeryForm');
                var token = $('input[name="__RequestVerificationToken"]', form).val();
                $.ajax({
                    url: "/NSLSL/Search/DownloadSearchResults",
                    cache: false,
                    type: "POST",
                    data: { __RequestVerificationToken: token, model: model },
                    contentType: 'application/x-www-form-urlencoded; charset=utf-8',
                    success: function (data) {
                        var fileName = "NSLSL-Results-";
                        switch (model.ExportOptions.Format)
                        {
                            case "csv":
                                fileName = fileName + "CSV.csv";
                                break;
                            case "abstract":
                                fileName = fileName + "Abstract.txt";
                                break;
                            case "summary":
                                fileName = fileName + "Summary.txt";
                                break;
                            case "xls":
                                fileName = fileName + "AllFields.xlsx";
                                break;
                        }

                        //Convert Base64 string to Byte Array.
                        var bytes = Base64ToBytes(data);

                        //Convert the Byte Data to BLOB object.
                        var blob = new Blob([bytes], { type: "application/octetstream" });

                        //Check the Browser type and download the File.
                        var isIE = false || !!document.documentMode;
                        if (isIE) {
                            window.navigator.msSaveBlob(blob, fileName);
                        } else {
                            var url = window.URL || window.webkitURL;
                            link = url.createObjectURL(blob);
                            var a = $("<a id='tempLink' />");
                            a.attr("download", fileName);
                            a.attr("href", link);
                            $("body").append(a);
                            a[0].click();
                            $("#tempLink").remove();
                        }
                        toastr.success("Results download/save successfully started");
                    },
                    error: function (jqXHR, textStatus, errorThrown) {
                        toastr.error("The resulting file contains too much data and cannot be processed. Please reduce the number of results to save.");
                    },
                    beforeSend: function (jqXHR, settings) {
                        $("#save-icon").removeClass("fa-download");
                        $("#save-icon").addClass("spinner spinner-border spinner-border-sm");
                    },
                    complete: function (jqXHR, settings) {
                        $("#save-icon").addClass("fa-download");
                        $("#save-icon").removeClass("spinner spinner-border spinner-border-sm");
                    }
                });
            });

            $('body').on("change", ".pubSelected", function () {
                var pubid = $(this).data('pubid');
                if (this.checked) {
                    selectedPubIds.push(pubid);
                } else {
                    var index = selectedPubIds.indexOf(pubid);
                    if (index !== -1) {
                        selectedPubIds.splice(index, 1);
                    }
                }

                // Set the text for the selected results dropdown options for emailing/saving
                $(".selectionOptions option[value='selected']").text("Selected Results (" + selectedPubIds.length + ")");
            });

            $('body').on("change", "#selectAll", function () {
                var selectAll = this.checked;
                var model = createModel(1);
                var pubIds;
                var token = $('input[name="__RequestVerificationToken"]', $('#__AjaxAntiForgeryForm')).val();
                $.ajax({
                    url: "/NSLSL/Search/SelectAllCheckedAjax",
                    cache: false,
                    type: "POST",
                    data: { __RequestVerificationToken: token, model: model },
                    contentType: 'application/x-www-form-urlencoded; charset=utf-8',
                    success: function (data) {
                        // Clear our selected publications array.
                        selectedPubIds = [];
                        $(".pubSelected").each(function () {
                            $(this).prop('checked', selectAll);
                        });

                        if (selectAll) {
                            data.forEach(function (id) {
                                selectedPubIds.push(id);
                            });
                        }

                        // Set the text for the selected results dropdown options for emailing/saving
                        $(".selectionOptions option[value='selected']").text("Selected Results (" + selectedPubIds.length + ")");

                    },
                    error: function (jqXHR, textStatus, errorThrown) {
                        $("#loadingMessage").hide();
                        alert(jqXHR.responseText);
                    },
                    beforeSend: function (jqXHR, settings) {
                        $("#loadingMessage").show();
                    }
                })

                if (selectAll) {
                    $("#selectAllLabel").text("Deselect all Results");
                }
                else {
                    $("#selectAllLabel").text("Select all Results");
                }
            });
        });

        function setSelectedPubCheckboxes() {
            $(".pubSelected").each(function () {
                var pubid = $(this).data('pubid');
                if (selectedPubIds.indexOf(pubid) !== -1) {
                    this.checked = true;
                }
            });
}

        // Global array for holding selected pubs for emailing or saving
        var selectedPubIds = [];

		$(function(btnClicked) {

            $("#cancelButton").click(function () {
                window.location.href = "/Search";
            });
        });

        function buildDefaultFilterCriteria(){
            var filterString;

            // Check all the checkboxes

            var defaultFilterCriteria = '';

            $(".defaultFilter").each(function (index) {
                if (this.checked) {
                    var fldName = $(this).data("filterfield");
                    var fldType = $(this).data("filtertype");

                    switch (fldName)
                    {
                        case "year":
                            defaultFilterCriteria = defaultFilterCriteria + ' BETWEEN (' + (new Date().getFullYear() - $(this).data("filtervalue")) + ':3001' + '[Pub Year])'
                            break;

                        case "notempty":
                            defaultFilterCriteria = defaultFilterCriteria + ' NOTEMPTY ([' + $(this).data("filtervalue") +'])';
                            break;

                        default:
                            defaultFilterCriteria = defaultFilterCriteria + ' CONTAINS ('+ $(this).data("filtervalue") + '[' + fldName + '])';
                            break;
                    }
                }
            });

            // If values in fromPubYear or toPubYear fields add that to our criteria.
            var fromYear = $("#fromPubYear").val();
            var toYear = $("#toPubYear").val();
            if ((fromYear != '' || toYear != '') && $("#customRange").is(':checked')) {
                // If we only have one or the other, then set the empty one to a value
                if (fromYear === '') {
                    fromYear = 1001;
                } else if (toYear === '') {
                    toYear = 3000;
                }

                defaultFilterCriteria = defaultFilterCriteria + ' BETWEEN (' + fromYear + ':' + toYear + '[Pub Year])'
            }

            $("#DefaultFilterCriteria").val(defaultFilterCriteria);
        }

        function createModel(fetchPageNumber) {
            var searchType = $("#advancedSearchDisplay").is(':visible') ? 'advanced' : 'simple';

            if (searchType == 'advanced') {
                var searchCriteria = $("#queryBox").val();
            } else {
                var searchCriteria = $("#searchCriteria").val();
            }

            var model = {
                PageFormat: $("#PageFormat").val(),
                CurrentPage: fetchPageNumber,
                SortBy: $("#SortBy").val(),
                SearchCriteria: searchCriteria,
                NumberPerPage: $("#NumberPerPage").val(),
                DefaultFilterCriteria: $("#DefaultFilterCriteria").val(),
                SortAscending: $("#OptionSortAscending").hasClass("fa fa-sort-amount-down-alt"),
                SelectAllChecked: $("#selectAll").prop('checked'),
                ExportOptions: {}
            };

            return model;
        }

        function createModelForExport(fetchPageNumber, exportType) {

            // Need to set the properties on our model for what is selected.
            var selectionOpt;
            var selectedIds = [];
            var email;
            var format;
            if (exportType == "email") {
                format = $("#FormatOptionForEmail").find(':selected').val();
                selectionOpt = $("#SelectionOptionForEmail").find(':selected').val();
                email = $("#emailTo").val();
            } else {
                format = $("#FormatOptionForSave").find(':selected').val();
                selectionOpt =  $("#SelectionOptionForSave").find(':selected').val();
            }

            // If the selctionOpt is allOnPage or selected, then build the array of ids for the model. If it's all, then the manager will handle it.
            switch (selectionOpt) {

                case "allOnPage":
                    $(".pubSelected").each(function() {
                        selectedIds.push($(this).data("pubid"));
                    });

                    break;

                case "selected":
                    selectedIds = selectedPubIds;

                    break;
            }
            if (exportType == "email") {
                if (selectedIds.length > 1000 || (selectionOpt == "all" && $("#searchResultCount").val() > 1000)) {
                    $("#emailMaxMsg").addClass("text-danger");
                    return null;
                }
            } else {
                if (selectedIds.length > 10000 || (selectionOpt == "all" && $("#searchResultCount").val() > 10000)) {
                    $("#saveMaxMsg").addClass("text-danger");
                    return null;
                }
            }
            var model = createModel(fetchPageNumber);

            // if the search criteria text is blank (the querybox input or the searchCriteria input), then use the hidden variable for the SearchCriteria from our model.
            // We may have gotten to the page via a link (SearchForIds for example)
            if (model.SearchCriteria == '') {
                model.SearchCriteria = $("#SearchCriteria").val();
            }
            model.ExportOptions.Type = exportType;
            model.ExportOptions.Selection = selectionOpt;
            model.ExportOptions.Format = format;
            model.ExportOptions.SelectedItems = selectedIds;
            model.ExportOptions.EmailAddress = email;

            return model;
        }

        function addToQueryBox(btnClicked) {

            if ($("#searchValue").val() === '' && !$("#searchFromValue").val() && !$("#searchToValue").val()) {
                $("#emptySearchTerm").html("Please enter a value before adding to query.")
                $("#emptySearchTerm").removeClass('d-none');
                return;
            }


            $("#emptySearchTerm").addClass('d-none');

            var operator = btnClicked.data("operator");

            // Change the text of the add button to AND and show the NOT and OR buttons if this is not our first add.
            if (btnClicked.text() != "AND" && operator === "AND") {
                btnClicked.text("AND");
                $("#btnNot").removeClass('d-none');
                $("#btnOr").removeClass('d-none');
            }

            // Get the selected field from the select list and the field type
            var field = $("#searchOptions").find(':selected').text();
            var fieldType = $("#searchOptions").find(':selected').data("columntype");

            // Build our new search term entry
            if (fieldType === "string") {
                var newSearchTerm = $("#searchValue").val() + "[" + field + "]";
            } else {
                var from = $("#searchFromValue").val();
                var to = $("#searchToValue").val();
                if (!from) {
                    from = 0;
                }
                if (!to) {
                    to = 3000;
                }
                var newSearchTerm = from + ":" + to + "[" + field + "]";
            }

            // If our queryBox already has content then enclose that content with parenthesis
            var qry = $("#queryBox")
            if (qry.val() === '') {
                $("#queryBox").val(newSearchTerm)
            } else {
                $("#queryBox").val("(" + $("#queryBox").val() + ") " + operator + " (" + newSearchTerm + ")");
            }


            // Set the value for the search criteria textbox and query box with the new value

            $("#searchCriteria").val($("#queryBox").val());
            $("#searchValue").val('');
            $(".btnSearch").removeClass('disabled');
}

        function changeSortIcon(span) {
            if (span.hasClass('fa-sort-amount-down-alt')) {
                span.removeClass('fa-sort-amount-down-alt');
                span.addClass('fa-sort-amount-down');
                $(".btn-sortdirection").attr("title", "Sorted Descending");

            } else {
                span.removeClass('fa-sort-amount-down');
                span.addClass('fa-sort-amount-down-alt');
                $(".btn-sortdirection").attr("title", "Sorted Ascending");
            }
}

