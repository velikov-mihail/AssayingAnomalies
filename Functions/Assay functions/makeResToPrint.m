function Results = makeResToPrint(ResStruct)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It creates a structure that is used to print the .tex latex file 
% and create the .pdf figures. 
%------------------------------------------------------------------------------------------
% USAGE:   
% Results = makeResToPrint(ResStruct)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - ResStruct - structure with results from the tests in the
%                      protocol
%------------------------------------------------------------------------------------------
% Output:
%        - Results - structure with results that are used to print the .tex
%                    latex file and .pdf figures
%------------------------------------------------------------------------------------------
% Examples:
%
% Results = makeResToPrint(ResStruct)
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

% Timekeeping
fprintf('\nNow working on preparing the results for printing. Run started at %s.\n', char(datetime('now')));

% Turn off warnings
warning('off','all')

% Store the individual structures from ResStruct
resBasicSorts    = ResStruct.resBasicSorts;
resCondMeSorts   = ResStruct.resCondMeSorts;
resCorrels       = ResStruct.resCorrels;
resAnoms         = ResStruct.resAnoms;
resCondSort      = ResStruct.resCondSort;
resFMBs          = ResStruct.resFMBs;
resCloseFMB      = ResStruct.resCloseFMB;
resCloseSpan     = ResStruct.resCloseSpan;
Z                = ResStruct.Z;
dendrogramLabels = ResStruct.dendrogramLabels;
cutoff           = ResStruct.cutoff;
labels           = ResStruct.labels;
combStrats       = ResStruct.combStrats;
testSignal       = ResStruct.testSignal;
signalLabel      = ResStruct.signalLabel;
closeLabels      = ResStruct.closeLabels;
timePeriod       = ResStruct.timePeriod;

% Load some variables
load dates
load pdates
load me
load ret
load ff
load ff_tc
load tcostsType

% Initialize the ouput structure
Results = struct;

% Create a character array of the name of the signal
signalChar = char(signalLabel);

% Figure 1
% Panel A
Results.Fig_Cov.PanelA.x = pdates;
Results.Fig_Cov.PanelA.y = [prctile(testSignal,[25 50 75],2) ...
                            mean(testSignal, 2, 'omitnan')];
Results.Fig_Cov.PanelA.xlim = pdates(ismember(dates,timePeriod));

% Panel B
Results.Fig_Cov.PanelB.x = pdates;
Results.Fig_Cov.PanelB.y = [sum(isfinite(testSignal),2)./sum(isfinite(me),2) ...
                            sum(isfinite(testSignal).*me, 2, 'omitnan')./sum(me, 2, 'omitnan')];
Results.Fig_Cov.PanelB.xlim = pdates(ismember(dates,timePeriod));



% Table 1
% Panel A
Results.Tab_BasicSort.PanelA.a = [resBasicSorts(1,1).res.xret'; 
                                  resBasicSorts(1,1).res.alpha';
                                  resBasicSorts(1,2).res.alpha';
                                  resBasicSorts(1,3).res.alpha';
                                  resBasicSorts(1,4).res.alpha';
                                  resBasicSorts(1,5).res.alpha';]; 
Results.Tab_BasicSort.PanelA.tA = [resBasicSorts(1,1).res.txret'; 
                                   resBasicSorts(1,1).res.talpha';
                                   resBasicSorts(1,2).res.talpha';
                                   resBasicSorts(1,3).res.talpha';
                                   resBasicSorts(1,4).res.talpha';
                                   resBasicSorts(1,5).res.talpha';]; 
Results.Tab_BasicSort.PanelA.h =  {'$r^e$','$\alpha_{CAPM}$','$\alpha_{FF3}$','$\alpha_{FF4}$','$\alpha_{FF5}$','$\alpha_{FF6}$'};

% Panel B
Results.Tab_BasicSort.PanelB.a = [resBasicSorts(1,5).res.factorLoadings.b]';
Results.Tab_BasicSort.PanelB.tA = [resBasicSorts(1,5).res.factorLoadings.t]'; 
h =  upper([resBasicSorts(1,5).res.factorLoadings.label]');
Results.Tab_BasicSort.PanelB.h = cellfun(@(x) strcat('$\beta_{\text{',x,'}}$'),h,'UniformOutput',0);


% Panel C
Results.Tab_BasicSort.PanelC.a = [mean(resBasicSorts(1,1).res.ptfNumStocks(:,1:5), 1, 'omitnan'); ...
                                  mean(resBasicSorts(1,1).res.ptfMarketCap, 1, 'omitnan')/1e3];
Results.Tab_BasicSort.PanelC.h = {'$n$','me $(\$10^6)$'};



% Table 2
% Panel A
nSorts = size(resBasicSorts, 1);
nModels = size(resBasicSorts, 2);
a = nan(nSorts, nModels+1);
tA = nan(nSorts, nModels+1);
for i=1:nSorts
    a(i,1) = resBasicSorts(i,1).res.xret(end);
    tA(i,1) = resBasicSorts(i,1).res.txret(end);
    for j=1:nModels
        a(i,j+1) = resBasicSorts(i,j).res.alpha(end);
        tA(i,j+1) = resBasicSorts(i,j).res.talpha(end);
    end
end
Results.Tab_RobustSort.PanelA.a = a;
Results.Tab_RobustSort.PanelA.tA = tA;
Results.Tab_RobustSort.PanelA.h = {'Quintile & NYSE & VW'; ...
                                   'Quintile & NYSE & EW';  ...
                                   'Quintile & Name & VW'; ...
                                   'Quintile & Cap & VW';  ...
                                   'Decile & NYSE & VW'}; 

% Panel B
a = nan(nSorts, nModels+1);
tA = nan(nSorts, nModels+1);
for i=1:nSorts
    a(i,1) = resBasicSorts(i,1).res.netxret;
    tA(i,1) = resBasicSorts(i,1).res.tnetxret;
    for j=1:nModels
        a(i,j+1) = resBasicSorts(i,j).gen_alpha_res.beta(1);
        tA(i,j+1) = resBasicSorts(i,j).gen_alpha_res.tstat(1);
    end
end
Results.Tab_RobustSort.PanelB.a = a;
Results.Tab_RobustSort.PanelB.tA = tA;
Results.Tab_RobustSort.PanelB.h = {'Quintile & NYSE & VW'; ...
                                   'Quintile & NYSE & EW';  ...
                                   'Quintile & Name & VW'; ...
                                   'Quintile & Cap & VW';  ...
                                   'Decile & NYSE & VW'}; 



% Table 3
% Panel A: Averge returns and strategy results
nMePtfs = size(resCondMeSorts, 1);
nModels = size(resCondMeSorts, 2);
a = nan(nMePtfs, nMePtfs+nModels+2);
tA = nan(nMePtfs, nMePtfs+nModels+2);
b = nan(nMePtfs, nMePtfs+nModels+1);
h = cell(nMePtfs, 1);
for i=1:nMePtfs
    h(i) = {[' & (',char(num2str(i)),')']};
    a(i,1:nMePtfs+2) = [resCondMeSorts(i,1).res.xret(1:end-1)' nan resCondMeSorts(i,1).res.xret(end)];
    tA(i,1:nMePtfs+2) = [resCondMeSorts(i,1).res.txret(1:end-1)' nan resCondMeSorts(i,1).res.txret(end)];
    b(i,1:nMePtfs) = mean(resCondMeSorts(i,1).res.ptfNumStocks(:,1:5), 1, 'omitnan');
    b(i,nMePtfs+2:2*nMePtfs+1) = mean(resCondMeSorts(i,1).res.ptfMarketCap, 1, 'omitnan')/1e3;    
    for j=1:nModels
        a(i,nMePtfs+2+j) = resCondMeSorts(i,j).res.alpha(end);
        tA(i,nMePtfs+2+j) = resCondMeSorts(i,j).res.talpha(end);        
    end
end
Results.Tab_CondSizeSort.PanelA.a = a;
Results.Tab_CondSizeSort.PanelA.tA = tA;
Results.Tab_CondSizeSort.PanelA.h = h; 

% Panel B: Number of stocks and market capitalization of portfolios
Results.Tab_CondSizeSort.PanelB.a = b;
Results.Tab_CondSizeSort.PanelB.tA = b;
Results.Tab_CondSizeSort.PanelB.h = h; 


% Store some anomaly performance statistics
count = 1;
for i=1:length(resAnoms)
    if ~isempty(resAnoms(i).xret)
        a(count,1) = resAnoms(i).sharpe(end);                              % Sharpe ratio of the anomalies
        a(count,2) = sqrt(12) * ...                                        % Net Sharpe ratio of the anomalies 
                     mean(resAnoms(i).netpret,'omitnan') / ...
                     std(resAnoms(i).netpret,'omitnan'); 
        a(count,3) = resCondSort(i).txret(end);                            % T-stat on conditional double sort
        res = (nanols(resBasicSorts(1,1).res.pret(:,end), ...
                     [ones(size(resBasicSorts(1,1).res.pret(:,end))) ...
                     resAnoms(i).pret(:,end)]));
        a(count,4) = res.tstat(1);                                         % T-stat on alpha from spanning test        
        a(count,5) = resCorrels(i,1);
        a(count,6) = resCorrels(i,2);  
        a(count,7) = resFMBs(i).t(2);
        count = count+1;
    end
end


% Figure 2
% Panel A
Results.Fig_SharpeDist.PanelA.Hist = a(:,1);
Results.Fig_SharpeDist.PanelA.Line = resBasicSorts(1,1).res.sharpe(end);
Results.Fig_SharpeDist.PanelA.xlim = [-2 2];

% Panel B
Results.Fig_SharpeDist.PanelB.Hist = a(:,2);
Results.Fig_SharpeDist.PanelB.Line = sqrt(12)*mean(resBasicSorts(1,1).res.netpret, 'omitnan') / ...
                                              std(resBasicSorts(1,1).res.netpret, 'omitnan');
Results.Fig_SharpeDist.PanelB.xlim = [-2 2];




% Figure 5
Results.Fig_CondAnoms.PanelA.Hist = a(:,7);
Results.Fig_CondAnoms.PanelB.Hist = a(:,4);
Results.Fig_CondAnoms.PanelC.Hist = a(:,3);


% Figure 6
ind = isfinite(a(:,5));
Results.Fig_Correls.PanelA.x = 100*a(ind,5);
Results.Fig_Correls.PanelA.lbl = labels.short(ind);

ind = isfinite(a(:,6));
Results.Fig_Correls.PanelB.x = 100*a(ind,6);
Results.Fig_Correls.PanelB.lbl = labels.short(ind);



% Create Figure 3 (Ibbotson)
nAnoms = length(resAnoms);
s = find(dates==timePeriod(1)+1);
e = find(dates==timePeriod(end));

% Store the gross & net test signal returns
pretGrossTestSignal = [resBasicSorts(1,1).res.pret(s:e, end)];
pretNetTestSignal = [resBasicSorts(1,1).res.netpret(s:e, end)];

% Store the gross & net anomaly returns
pretGrossAnoms = nan(e-s+1, nAnoms);
pretNetAnoms = nan(e-s+1, nAnoms);
for i=1:nAnoms
    pretGrossAnoms(:,i) = resAnoms(i).pret(s:e, end);
    pretNetAnoms(:,i) = resAnoms(i).netpret(s:e, end);
end

% Fill in the missing anomalies with the return signal
for i = 1:nAnoms
    rNan = find(isnan(pretGrossAnoms(:,i)), 1, 'last');
    if ~isempty(rNan)
        pretGrossAnoms(1:rNan, i) = pretGrossTestSignal(1:rNan);
        pretNetAnoms(1:rNan, i) = pretNetTestSignal(1:rNan);
    end
end

% Store in the structure
Results.Fig_Ibbots.pretGrossTestSignal = pretGrossTestSignal;
Results.Fig_Ibbots.pretNetTestSignal = pretNetTestSignal;
Results.Fig_Ibbots.pretGrossAnoms = pretGrossAnoms;
Results.Fig_Ibbots.pretNetAnoms = pretNetAnoms;
Results.Fig_Ibbots.dates = dates(s:e);


% Figure 4 - alphas
nAnoms = length(labels.short);
nModels = size(resBasicSorts, 2);
alpha_gross = nan(nAnoms, nModels);
alpha_net = nan(nAnoms, nModels);
for i = 1:nAnoms
    % Store the returns & tcosts for this anomaly
    anomRet = resAnoms(i).pret(:, end);
    anomTcosts = resAnoms(i).tcostsTS;
    
    % Find the sample for which it is available
    s = find(isfinite(anomRet + anomTcosts), 1, 'first');
    e = find(isfinite(anomRet + anomTcosts), 1, 'last');
    
    % Loop through the factor models
    count = 1;
    for f = [1 3 4 5 6] 
        switch f
            % CAPM
            case 1
                factorRet = mkt;            
                factorTcosts = mkt_tc;     
            % FF3    
            case 3
                factorRet = [mkt smb hml]; 
                factorTcosts = [mkt_tc smb_tc hml_tc]; 
            % FF4
            case 4
                factorRet = [mkt smb hml umd]; 
                factorTcosts = [mkt_tc smb_tc hml_tc umd_tc]; 
            % FF5
            case 5
                factorRet = [mkt smb hml rmw cma]; 
                factorTcosts = [mkt_tc smb_tc hml_tc rmw_tc cma_tc]; 
            % FF6
            case 6
                factorRet = [mkt smb hml rmw cma umd]; 
                factorTcosts = [mkt_tc smb_tc hml_tc rmw_tc cma_tc umd_tc]; 
        end
        
        % Gross alpha
        res = nanols(anomRet(s:e), [const(s:e) factorRet(s:e,:)]);
        alpha_gross(i,count) = res.beta(1);
        
        res = calcGenAlpha(anomRet(s:e), anomTcosts(s:e), factorRet(s:e,:), factorTcosts(s:e,:), 0);
        alpha_net(i,count) = res.beta(1);
        count = count+1;
    end
end

% Set the NaN generalized alphas to zero
alpha_net(isnan(alpha_net)) = 0;

% Create the percentiles
alpha_gross_prct = prctile(alpha_gross, 0:99, 1); 
alpha_net_prct = prctile(alpha_net, 0:99, 1); 

% Save the test signal gross & net alphas
testSignalGrossAlpha = nan(1, nModels);
testSignalNetAlpha = nan(1, nModels);
for i = 1:nModels
    testSignalGrossAlpha(1, i) = resBasicSorts(1, i).res.alpha(end);
    testSignalNetAlpha(1, i) = resBasicSorts(1, i).gen_alpha_res.beta(1);
end
testSignalNetAlpha(isnan(testSignalNetAlpha)) = 0;

testSignalGrossAlphaPrct = nan(1, nModels);
testSignalNetAlphaPrct = nan(1, nModels);
for i = 1:5
    testSignalGrossAlphaPrct(1, i) = invprctile(alpha_gross(:,i),testSignalGrossAlpha(i));
    testSignalNetAlphaPrct(1, i) = invprctile(alpha_net(:,i),testSignalNetAlpha(i));
end

% Panel A
Results.Fig_AlphaPrctl.PanelA.y = alpha_gross_prct;
Results.Fig_AlphaPrctl.PanelA.x = (0:99)';
Results.Fig_AlphaPrctl.PanelA.dx = testSignalGrossAlphaPrct;
Results.Fig_AlphaPrctl.PanelA.dy = testSignalGrossAlpha;

% Panel B
Results.Fig_AlphaPrctl.PanelB.y = alpha_net_prct;
Results.Fig_AlphaPrctl.PanelB.x = (0:99)';
Results.Fig_AlphaPrctl.PanelB.dx = testSignalNetAlphaPrct;
Results.Fig_AlphaPrctl.PanelB.dy = testSignalNetAlpha;

% Figure 7
Results.Fig_Dendrogram.Z = Z;
Results.Fig_Dendrogram.dendrogramLabels = dendrogramLabels;
Results.Fig_Dendrogram.cutoff = cutoff;


% Table 4
nCloseAnoms = length(closeLabels.long);
h = [{'Intercept'}, signalLabel, cell(1, nCloseAnoms)];
for i = 1:nCloseAnoms
    h(i+2) = {['Anomaly ', char(num2str(i))]};
end
a = nan(nCloseAnoms+2, nCloseAnoms+1);
tA = nan(nCloseAnoms+2, nCloseAnoms+1);
for i = 1:nCloseAnoms
    a(1:2, i) = resCloseFMB(i).bhat(1:2)';
    tA(1:2, i) = resCloseFMB(i).t(1:2)';
    a(i+2, i) = resCloseFMB(i).bhat(3);
    tA(i+2, i) = resCloseFMB(i).t(3);    
end
a(:,end) = resCloseFMB(nCloseAnoms+1).bhat';
tA(:,end) = resCloseFMB(nCloseAnoms+1).t';
Results.Tab_CloseFMB.a = a;
Results.Tab_CloseFMB.tA = tA;
Results.Tab_CloseFMB.h = h;


% Table 5
nCloseAnoms = length(closeLabels.long);
h = [{'Intercept'}, cell(1, nCloseAnoms)];
for i = 1:nCloseAnoms
    h(i+1) = {['Anomaly ', char(num2str(i))]};
end
h = [h, {'mkt','smb','hml','rmw','cma','umd'}];
a = nan(nCloseAnoms+7, nCloseAnoms+1);
tA = nan(nCloseAnoms+7, nCloseAnoms+1);
for i = 1:nCloseAnoms
    a(1, i) = resCloseSpan(i).beta(1);
    tA(1, i) = resCloseSpan(i).tstat(1);
    a(i+1, i) = resCloseSpan(i).beta(2);
    tA(i+1, i) = resCloseSpan(i).tstat(2);    
    a(nCloseAnoms+2:end, i) = resCloseSpan(i).beta(3:end);
    tA(nCloseAnoms+2:end, i) = resCloseSpan(i).tstat(3:end);
end
a(:,end) = resCloseSpan(nCloseAnoms+1).beta';
tA(:,end) = resCloseSpan(nCloseAnoms+1).tstat';
Results.Tab_CloseSpan.a = 100*a;
Results.Tab_CloseSpan.tA = tA;
Results.Tab_CloseSpan.h = h;


% Figure 8
% Drop the ones with errors
indKeep = ~contains({combStrats(:).label},{'N/A'});
nCombStrats = sum(indKeep);
combStrats = combStrats(indKeep);

s = find(dates==timePeriod(1));
e = find(dates==timePeriod(end));
yWithout = nan(e-s+1, nCombStrats);
yWith = nan(e-s+1, nCombStrats);
ttl = cell(1, nCombStrats);
explanation = cell(1, nCombStrats);
for i=1:size(combStrats,1)
    ind = makeUnivSortInd(combStrats(i).eret,10);
    res1 = runUnivSort(ret, ind, dates, me, 'weighting', 'v', ...
                                            'timePeriod', timePeriod, ...
                                            'plotFigure', 0, ...
                                            'printResults', 0); 
    ind = makeUnivSortInd(combStrats(i).eret_enh,10);
    res2 = runUnivSort(ret, ind, dates, me, 'weighting', 'v', ...
                                            'timePeriod', timePeriod, ...
                                            'plotFigure', 0, ...
                                            'printResults', 0); 

    yWithout(:, i) = res1.pret(:,end);                                    
    yWith(:, i) = res2.pret(:,end);                                    
    ttl(i) = cellstr(combStrats(i).label);
    explanation(i) = (combStrats(i).explanation);
end
% Add to the output structure
Results.Fig_CombStrat.x = res1.dates;
Results.Fig_CombStrat.yWithout = yWithout;
Results.Fig_CombStrat.yWith = yWith;
Results.Fig_CombStrat.ttl = ttl;
Results.Fig_CombStrat.explanation = explanation;


% Store a few more characters
Results.Text.timePeriod = timePeriod;
Results.Text.nAnoms = char(num2str(length(Results.Fig_SharpeDist.PanelA.Hist)));
Results.Text.signalChar = upper(signalChar);
Results.Text.sharpeChar = sprintf('%1.2f',resBasicSorts(1,1).res.sharpe(end));
Results.Text.netSharpeChar = sprintf('%1.2f', sqrt(12)*mean(resBasicSorts(1,1).res.netpret, 'omitnan')/std(resBasicSorts(1,1).res.netpret, 'omitnan'));
Results.Text.nCloseAnoms = length(closeLabels.long);
Results.Text.closeAnoms = char(closeLabels.long(1));
for i = 2:Results.Text.nCloseAnoms
    Results.Text.closeAnoms = [Results.Text.closeAnoms, ', ', char(closeLabels.long(i))]; 
end
Results.Text.closeAnomLabels = closeLabels.long;
Results.signalInfo = ResStruct.signalInfo;
Results.Text.tcostsType = tcostsType;

% Timekeeping
fprintf('Preparation of results for printing ended at %s.\n', char(datetime('now')));
