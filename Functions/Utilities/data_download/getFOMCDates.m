function fomcDates = getFOMCDates()
% PURPOSE: This function downloads FOMC meeting dates from the Fed's FOMC
% calendar
%------------------------------------------------------------------------------------------
% USAGE:   
% fomcDates = getFOMCDates()
%------------------------------------------------------------------------------------------
% Required Inputs:
%------------------------------------------------------------------------------------------
% Output:
%        -fomcDates - A datetime vector with all FOMC dates
%------------------------------------------------------------------------------------------
% Examples:
%
% fomcDates = getFOMCDates()
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

fomcURL = 'http://www.federalreserve.gov/monetarypolicy/fomccalendars.htm';

last5yrsData = webread(fomcURL,'options','text');

% Parse it 
fomcCalTree = htmlTree(last5yrsData);

% Find all the .htm links & store into subtrees
selector = "a[href$="".htm""]";
htmlSubTrees = findElement(fomcCalTree,selector);
attr = "href";
htmLink = cellstr(getAttribute(htmlSubTrees, attr));

selector = "a[href$="".pdf""]";
pdfSubTrees = findElement(fomcCalTree,selector);
attr = "href";
pdfLink = cellstr(getAttribute(pdfSubTrees, attr));

allLinks = [htmLink; pdfLink];

% Find all the links to minutes of FOMC meetings (which will give us the
% dates)
indToKeep = contains(allLinks,'minutes') | ...
            contains(allLinks,'fomcmoa');
fomcMinutesLinks = allLinks(indToKeep);

last5yrsDates = unique(datetime(cellfun(@(x) x(regexp(x,'(\d+_?){8}'):regexp(x,'(\d+_?){8}')+7),fomcMinutesLinks,'UniformOutput',0),'InputFormat','yyyyMMdd'));

% Get the historical ones
fomcMeetingDates = last5yrsDates;

e = year(datetime('now'))-6;

for i=1936:e
    fomcURL = ['https://www.federalreserve.gov/monetarypolicy/fomchistorical',char(num2str(i)),'.htm'];

    thisYearData = webread(fomcURL,'options','text');

    % Parse it 
    fomcCalTree = htmlTree(thisYearData);

    % Find all the .htm links & store into subtrees
    selector = "a[href$="".htm""]";
    htmlSubTrees = findElement(fomcCalTree,selector);
    attr = "href";
    htmLink = cellstr(getAttribute(htmlSubTrees, attr));

    selector = "a[href$="".pdf""]";
    pdfSubTrees = findElement(fomcCalTree,selector);
    attr = "href";
    pdfLink = cellstr(getAttribute(pdfSubTrees, attr));

    allLinks = [htmLink; pdfLink];

    % Find all the links to minutes of FOMC meetings (which will give us the
    % dates)
    indToKeep = contains(allLinks,'Agenda');
    fomcMinutesLinks = allLinks(indToKeep);

    thisYearDates = unique(datetime(cellfun(@(x) x(regexp(x,'(\d+_?){8}'):regexp(x,'(\d+_?){8}')+7),fomcMinutesLinks,'UniformOutput',0),'InputFormat','yyyyMMdd'));
    
    fomcMeetingDates = [fomcMeetingDates; thisYearDates];
end


fomcDates=sort(fomcMeetingDates);

