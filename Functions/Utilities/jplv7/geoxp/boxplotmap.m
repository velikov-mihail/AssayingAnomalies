function [out]=boxplotmap(long,lat,variable,varargin)
% PURPOSE: This function links a map and a box and whiskers plot (only the box and whiskers plot is active)
%------------------------------------------------------------------------
% USAGE: out=boxplotmap(long,,lat,variable,carte,label,symbol)
%   where : 
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           variable = n x 1 vector of the variable to study
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% MANUAL: Select points on  the box and whiskers plot by clicking with the left mouse button
%         Select quartiles on the box and whiskers plot by clicking with the left mouse button
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses selectstat.m
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
name=inputname(3);
%creation d'un menu pour sauver
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save boxplotfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
c=0;
l=0;
symbol=0;
% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        carte=varargin{1};
        c=1;
    end;
    if  t>=2 & ~isempty(varargin{2})
        label=varargin{2};
        l=1;
    end;
    if t==3 & ~isempty(varargin{3})
        symbol=varargin{3};
    end;
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Trace the map
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');
%%%%%%%%%%%%%%

% calcule median, quantiles and other usefull figures
med=prctile(variable,50);
q1=prctile(variable,25);
q3=prctile(variable,75);
frthaute=q3+1.5*(q3-q1);
frtbasse=q1-1.5*(q3-q1);
I=find(variable>=frtbasse);
vadjmin=min(variable(I));
I=find(variable<=frthaute);
vadjmax=max(variable(I));
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Trace box and whiskers plot
Axis2=subplot(1,2,2);
boxplot(variable);
title(name);
axis manual;
subplot(Axis1);
axis manual;
Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');
%%%%%%%%%%%%%%%%%%%%%

% Main loop
BUTTON=0;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    %redraw the graphs
    subplot(Axis2);
    hold on;
    cla;
    boxplot(variable);
    axis manual;
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    if ~isempty(Iselect)
        v=variable(Iselect);
        Iatyp=find(v>frthaute | v<frtbasse);
        Ityp=find(v<=frthaute & v>=frtbasse);
        if ~isempty(Iatyp)
            hold on;
            if symbol==1
                plot(ones(1,length(Iatyp)),v(Iatyp),'g*');
            else
                plot(ones(1,length(Iatyp)),v(Iatyp),'g+');
            end;
        end;
        if ~isempty(find(v(Ityp)<q1))
            rectangle('Position',[0.93 vadjmin 0.14 q1-vadjmin],'FaceColor','g');
        end;
        if ~isempty(find(v(Ityp)>=q1 & v(Ityp)<med))
            rectangle('Position',[0.93 q1 0.14 med-q1],'FaceColor','g');
        end;
        if ~isempty(find(v(Ityp)>=med & v(Ityp)<q3))
            rectangle('Position',[0.93 med 0.14 q3-med],'FaceColor','g');
        end;
        if ~isempty(find(v(Ityp)>q3))
            rectangle('Position',[0.93 q3 0.14 vadjmax-q3],'FaceColor','g');
        end;
    end;
    hold off;
    subplot(Axis1);
    hold on;
    cla;
    if c==1
            plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect)
      plot(long(Iunselect),lat(Iunselect),'b.');
    end;
    if ~isempty(Iselect)
        if symbol==1
             plot(long(Iselect),lat(Iselect),'g*');  
        else
             plot(long(Iselect),lat(Iselect),'g.');  
        end;           
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        obs=zeros(size(long,1),1);
    % box selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        if BUTTON~=3 & BUTTON~=2 
        obs=selectstat('box',obs,variable,frtbasse,frthaute,q1,med,q3,y);
        end;
    end;
    %%%%%%%%%%%%%%%%%%
end;
out=obs;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%